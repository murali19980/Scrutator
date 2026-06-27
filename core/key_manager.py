"""Secure credential management for Scrutator API keys."""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Soft import for keyring
try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    logger.warning("keyring package not found. System keychain integration is disabled.")

class KeyManager:
    @staticmethod
    def read_secret(key_name: str) -> Optional[str]:
        """Read a secret from Docker secret file first, then fall back to env var.
        
        Docker secrets are mounted at /run/secrets/<key_name_lowercase>.
        This prevents API keys from appearing in `docker inspect` or /proc/self/environ.
        """
        secret_path = f"/run/secrets/{key_name.lower()}"
        if os.path.exists(secret_path):
            try:
                with open(secret_path, "r") as f:
                    value = f.read().strip()
                if value:
                    return value
            except OSError as e:
                logger.warning(f"Failed to read Docker secret {secret_path}: {e}")
        return os.environ.get(key_name)

    @staticmethod
    def get_key(provider: str) -> Optional[str]:
        """Retrieve API key for the given provider securely.
        
        Tries:
        1. System keychain (keyring)
        2. Local encrypted keys file (~/.scrutator_keys.enc)
        3. Docker secret file (/run/secrets/<provider>_api_key)
        4. Environment variable (plaintext fallback)
        """
        provider_upper = provider.upper()
        
        # 1. Try system keychain first
        if KEYRING_AVAILABLE:
            try:
                key = keyring.get_password("scrutator", f"{provider_upper}_API_KEY")
                if key:
                    return key
            except Exception as e:
                logger.warning(f"Failed to retrieve key from system keychain: {e}")
        
        # 2. Try encrypted key file as fallback
        try:
            from cryptography.fernet import Fernet
            enc_file = os.path.expanduser("~/.scrutator_keys.enc")
            key_file = os.path.expanduser("~/.scrutator_master.key")
            
            if os.path.exists(enc_file) and os.path.exists(key_file):
                with open(key_file, "rb") as f:
                    master_key = f.read()
                with open(enc_file, "rb") as f:
                    encrypted_data = f.read()
                    
                f_obj = Fernet(master_key)
                decrypted = f_obj.decrypt(encrypted_data).decode("utf-8")
                
                # Parse decrypted data (key=value format)
                for line in decrypted.split("\n"):
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() == f"{provider_upper}_API_KEY":
                            return v.strip()
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to decrypt key file: {e}")

        # 3. Docker secret or plaintext environment fallback
        key = KeyManager.read_secret(f"{provider_upper}_API_KEY")
        if key:
            # Only warn if it came from env, not Docker secrets
            secret_path = f"/run/secrets/{provider_upper.lower()}_api_key"
            if not os.path.exists(secret_path):
                logger.warning(
                    f"Using plaintext API key from environment for {provider_upper}. "
                    "For better security, use Docker secrets or the system keychain."
                )
        return key

    @staticmethod
    def set_key(provider: str, key_value: str) -> bool:
        """Store API key for the given provider securely."""
        provider_upper = provider.upper()
        if not key_value:
            return False
            
        # 1. Try system keychain
        if KEYRING_AVAILABLE:
            try:
                keyring.set_password("scrutator", f"{provider_upper}_API_KEY", key_value)
                logger.info(f"Successfully saved {provider_upper}_API_KEY to system keychain.")
                return True
            except Exception as e:
                logger.warning(f"Failed to save key to system keychain: {e}")
                
        # 2. Try encrypted key file fallback
        try:
            from cryptography.fernet import Fernet
            enc_file = os.path.expanduser("~/.scrutator_keys.enc")
            key_file = os.path.expanduser("~/.scrutator_master.key")
            
            # Generate or load master key
            if os.path.exists(key_file):
                with open(key_file, "rb") as f:
                    master_key = f.read()
            else:
                master_key = Fernet.generate_key()
                with open(key_file, "wb") as f:
                    f.write(master_key)
                try:
                    os.chmod(key_file, 0o600)
                except Exception:
                    pass
            
            # Load existing keys
            existing_keys = {}
            if os.path.exists(enc_file):
                with open(enc_file, "rb") as f:
                    enc_data = f.read()
                f_obj = Fernet(master_key)
                try:
                    decrypted = f_obj.decrypt(enc_data).decode("utf-8")
                    for line in decrypted.split("\n"):
                        if "=" in line:
                            k, v = line.split("=", 1)
                            existing_keys[k.strip()] = v.strip()
                except Exception:
                    pass
                    
            # Update key
            existing_keys[f"{provider_upper}_API_KEY"] = key_value
            
            # Save and encrypt
            serialized = "\n".join(f"{k}={v}" for k, v in existing_keys.items())
            f_obj = Fernet(master_key)
            encrypted = f_obj.encrypt(serialized.encode("utf-8"))
            with open(enc_file, "wb") as f:
                f.write(encrypted)
            try:
                os.chmod(enc_file, 0o600)
            except Exception:
                pass
                
            logger.info(f"Successfully saved encrypted {provider_upper}_API_KEY to file.")
            return True
        except ImportError:
            logger.warning("cryptography package not found. Local file encryption fallback is disabled.")
        except Exception as e:
            logger.error(f"Failed to save key to file: {e}")
            
        return False

    @staticmethod
    def delete_key(provider: str) -> bool:
        """Delete API key for the given provider."""
        provider_upper = provider.upper()
        deleted = False
        
        # 1. Try system keychain
        if KEYRING_AVAILABLE:
            try:
                keyring.delete_password("scrutator", f"{provider_upper}_API_KEY")
                deleted = True
            except keyring.errors.PasswordDeleteError:
                pass
            except Exception as e:
                logger.warning(f"Failed to delete key from system keychain: {e}")
                
        # 2. Try encrypted key file
        try:
            from cryptography.fernet import Fernet
            enc_file = os.path.expanduser("~/.scrutator_keys.enc")
            key_file = os.path.expanduser("~/.scrutator_master.key")
            
            if os.path.exists(enc_file) and os.path.exists(key_file):
                with open(key_file, "rb") as f:
                    master_key = f.read()
                with open(enc_file, "rb") as f:
                    enc_data = f.read()
                    
                f_obj = Fernet(master_key)
                decrypted = f_obj.decrypt(enc_data).decode("utf-8")
                
                updated_lines = []
                for line in decrypted.split("\n"):
                    if "=" in line:
                        k, v = line.split("=", 1)
                        if k.strip() != f"{provider_upper}_API_KEY":
                            updated_lines.append(line)
                            
                serialized = "\n".join(updated_lines)
                encrypted = f_obj.encrypt(serialized.encode("utf-8"))
                with open(enc_file, "wb") as f:
                    f.write(encrypted)
                deleted = True
        except Exception:
            pass
            
        return deleted
