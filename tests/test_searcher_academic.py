"""Tests for AcademicSearcher module."""

import pytest
import respx
import httpx
from core.searcher_academic import AcademicSearcher

@pytest.fixture
def academic_searcher():
    # Load config automatically or pass None to load default
    return AcademicSearcher()

@respx.mock
def test_search_arxiv_success(academic_searcher):
    # Mock ArXiv API response
    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
        <entry>
            <id>http://arxiv.org/abs/1706.03762v5</id>
            <title>Attention Is All You Need</title>
            <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks...</summary>
            <published>2017-06-12T17:57:34Z</published>
            <author>
                <name>Ashish Vaswani</name>
            </author>
            <author>
                <name>Noam Shazeer</name>
            </author>
            <link rel="alternate" href="http://arxiv.org/abs/1706.03762"/>
            <link rel="alternate" title="doi" href="http://dx.doi.org/10.1007/12345"/>
        </entry>
    </feed>
    """
    respx.get("http://export.arxiv.org/api/query").mock(
        return_value=httpx.Response(200, text=xml_response)
    )
    
    # We temporarily bypass sleep rate limit for testing
    academic_searcher.rate_limits["arxiv"] = 0.0
    
    results = academic_searcher.search_arxiv("attention", max_results=1)
    assert len(results) == 1
    assert results[0]["title"] == "Attention Is All You Need"
    assert results[0]["authors"] == ["Ashish Vaswani", "Noam Shazeer"]
    assert results[0]["year"] == "2017"
    assert results[0]["doi"] == "10.1007/12345"
    assert results[0]["source"] == "arxiv"

@respx.mock
def test_search_pubmed_success(academic_searcher):
    # Mock PubMed search ID list Esearch
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi").mock(
        return_value=httpx.Response(
            200,
            json={
                "esearchresult": {
                    "idlist": ["12345"]
                }
            }
        )
    )
    
    # Mock PubMed abstracts Efetch
    xml_response = """<?xml version="1.0" encoding="UTF-8"?>
    <PubmedArticleSet>
        <PubmedArticle>
            <MedlineCitation>
                <PMID>12345</PMID>
                <Article>
                    <ArticleTitle>Method for DNA Sequencing</ArticleTitle>
                    <AuthorList>
                        <Author>
                            <LastName>Sanger</LastName>
                            <ForeName>Frederick</ForeName>
                        </Author>
                    </AuthorList>
                    <Journal>
                        <Title>Journal of Molecular Biology</Title>
                        <JournalIssue>
                            <PubDate>
                                <Year>1977</Year>
                            </PubDate>
                        </JournalIssue>
                    </Journal>
                    <Abstract>
                        <AbstractText>We describe a rapid method for determining nucleotide sequences in DNA.</AbstractText>
                    </Abstract>
                    <ELocationID EIdType="doi">10.1016/0022-2836(77)90044-6</ELocationID>
                </Article>
            </MedlineCitation>
        </PubmedArticle>
    </PubmedArticleSet>
    """
    respx.get("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi").mock(
        return_value=httpx.Response(200, text=xml_response)
    )
    
    academic_searcher.rate_limits["pubmed"] = 0.0
    
    results = academic_searcher.search_pubmed("dna sequencing", max_results=1)
    assert len(results) == 1
    assert results[0]["title"] == "Method for DNA Sequencing"
    assert results[0]["authors"] == ["Frederick Sanger"]
    assert results[0]["year"] == "1977"
    assert results[0]["doi"] == "10.1016/0022-2836(77)90044-6"
    assert results[0]["source"] == "pubmed"

@respx.mock
def test_search_openalex_success(academic_searcher):
    # Mock OpenAlex works search
    respx.get("https://api.openalex.org/works").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Quantum Computation",
                        "authorships": [
                            {"author": {"display_name": "Richard Feynman"}}
                        ],
                        "publication_year": 1982,
                        "doi": "https://doi.org/10.1007/BF01886518",
                        "abstract_inverted_index": {
                            "Simulating": [0],
                            "physics": [1],
                            "with": [2],
                            "computers": [3]
                        },
                        "primary_location": {
                            "source": {"display_name": "International Journal of Theoretical Physics"}
                        },
                        "id": "https://openalex.org/W12345"
                    }
                ]
            }
        )
    )
    
    academic_searcher.rate_limits["openalex"] = 0.0
    
    results = academic_searcher.search_openalex("feynman", max_results=1)
    assert len(results) == 1
    assert results[0]["title"] == "Quantum Computation"
    assert results[0]["authors"] == ["Richard Feynman"]
    assert results[0]["year"] == "1982"
    assert results[0]["doi"] == "10.1007/BF01886518"
    assert results[0]["summary"] == "Simulating physics with computers"
    assert results[0]["source"] == "openalex"
