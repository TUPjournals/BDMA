#!/usr/bin/env python3
"""Fetch BDMA 2026 article details and merge with existing data."""
import json
import re
import time
import requests
import html as html_mod

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

def extract_meta(html, name):
    """Extract meta tag content - try both attribute orders."""
    p1 = rf'<meta\s+name="{re.escape(name)}"\s+content="([^"]*)"'
    p2 = rf'<meta\s+content="([^"]*)"\s+name="{re.escape(name)}"'
    for p in [p1, p2]:
        m = re.findall(p, html)
        if m:
            return m
    return []

def clean_affiliation(raw):
    """Clean affiliation string."""
    cleaned = re.sub(r'\s*[\u4e00-\u9fff]+\s*', '', raw)
    cleaned = re.sub(r',\s*,+', ',', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip().strip(',').strip()
    country_end = re.compile(r',\s*([A-Z][A-Z\s]+?)\.\s*')
    splits = list(country_end.finditer(cleaned))
    if not splits:
        return [cleaned] if cleaned else []
    affiliations, start = [], 0
    for m in splits:
        affil = cleaned[start:m.end()].strip().rstrip('.').strip()
        if affil:
            affiliations.append(affil)
        start = m.end()
    remaining = cleaned[start:].strip()
    if remaining:
        affiliations.append(remaining)
    return affiliations

def fetch_article_details(doi):
    """Fetch article page and extract all metadata."""
    url = f'https://www.sciopen.com/article/{doi}'
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.encoding = 'utf-8'
        page = resp.text
    except Exception as e:
        print(f"  Error fetching {doi}: {e}")
        return None

    # Title
    title_match = re.search(r'<meta\s+name="citation_title"\s+content="([^"]*)"', page)
    title = title_match.group(1) if title_match else ''

    # Authors from JSON-LD
    authors = []
    jsonld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', page, re.DOTALL)
    if jsonld_match:
        try:
            data = json.loads(jsonld_match.group(1))
            if 'author' in data:
                for a in data['author']:
                    if isinstance(a, dict) and 'name' in a:
                        authors.append(a['name'])
        except:
            pass

    # Fallback: citation_author meta tags
    if not authors:
        authors = extract_meta(page, 'citation_author')

    # Abstract
    abstract = ''
    og_desc = re.search(r'<meta\s+property="og:description"\s+content="([^"]*)"', page)
    if og_desc:
        abstract = html_mod.unescape(og_desc.group(1))
        abstract = re.sub(r'<[^>]+>', '', abstract).strip()

    # Keywords
    keywords_raw = extract_meta(page, 'citation_keywords')
    keywords = [k.strip() for k in keywords_raw if k.strip()]

    # Dates from page text
    received = revised = accepted = published = ''
    date_pattern = r'(\d{1,2}\s+\w+\s+\d{4})'
    labels = {'Received': 'received', 'Revised': 'revised', 'Accepted': 'accepted', 'Published': 'published'}
    for label, field in labels.items():
        m = re.search(rf'{label}:\s*{date_pattern}', page)
        if m:
            if field == 'received':
                received = m.group(1)
            elif field == 'revised':
                revised = m.group(1)
            elif field == 'accepted':
                accepted = m.group(1)
            elif field == 'published':
                published = m.group(1)

    # Volume, issue, pages from citation meta
    vol_match = re.search(r'<meta\s+name="citation_volume"\s+content="([^"]*)"', page)
    iss_match = re.search(r'<meta\s+name="citation_issue"\s+content="([^"]*)"', page)
    sp_match = re.search(r'<meta\s+name="citation_firstpage"\s+content="([^"]*)"', page)
    ep_match = re.search(r'<meta\s+name="citation_lastpage"\s+content="([^"]*)"', page)

    volume = vol_match.group(1) if vol_match else ''
    issue = iss_match.group(1) if iss_match else ''
    firstpage = sp_match.group(1) if sp_match else ''
    lastpage = ep_match.group(1) if ep_match else ''

    # Publication date from citation meta
    pub_date_match = re.search(r'<meta\s+name="citation_publication_date"\s+content="([^"]*)"', page)
    publication_date = pub_date_match.group(1) if pub_date_match else ''

    # Online date
    online_date_match = re.search(r'<meta\s+name="citation_online_date"\s+content="([^"]*)"', page)
    online_date = online_date_match.group(1) if online_date_match else ''

    # Article type - BDMA doesn't have it, default to Research Article
    article_type = 'Research Article'

    # Internal ID from download_ris link
    internal_id = ''
    ris_link = re.search(r'download_ris\?tag=2&id=(\d+)', page)
    if ris_link:
        internal_id = ris_link.group(1)

    # Affiliations
    affil_raw = extract_meta(page, 'citation_author_institution')
    affiliations = [clean_affiliation(a) for a in affil_raw] if affil_raw else []

    return {
        'title': title,
        'authors': authors,
        'abstract': abstract,
        'keywords': keywords,
        'volume': volume,
        'issue': issue,
        'firstpage': firstpage,
        'lastpage': lastpage,
        'publication_date': publication_date,
        'online_date': online_date,
        'received': received,
        'revised': revised,
        'accepted': accepted,
        'published': published,
        'type': article_type,
        'internal_id': internal_id,
        'affiliations': affiliations,
    }

def main():
    # Load raw articles from issues 1-2
    with open('bdma_raw_articles.json', 'r', encoding='utf-8') as f:
        raw_articles = json.load(f)

    print(f"Fetching details for {len(raw_articles)} articles from issues 1-2...")

    results = []
    for i, article in enumerate(raw_articles):
        doi = article.get('doi', '')
        print(f"[{i+1}/{len(raw_articles)}] {doi}")

        details = fetch_article_details(doi)
        if not details:
            continue

        # Parse journalAndIssue for year
        ji_match = re.search(r'(\d{4}),\s*(\d+)\((\d+)', article.get('journalAndIssue', ''))
        year = ji_match.group(1) if ji_match else '2026'
        volume = ji_match.group(2) if ji_match else details['volume']
        issue = ji_match.group(3) if ji_match else details['issue']

        # Build article object matching existing format
        article_obj = {
            'doi': doi,
            'title': details['title'] or article.get('title', ''),
            'authors': details['authors'],
            'keywords': details['keywords'],
            'abstract': details['abstract'],
            'volume': volume,
            'issue': issue,
            'firstpage': details['firstpage'] or article.get('journalAndIssue', '').split(': ')[-1] if ': ' in article.get('journalAndIssue', '') else '',
            'lastpage': details['lastpage'],
            'year': int(year),
            'type': details['type'],
            'url': f'https://www.sciopen.com/article/{doi}',
            'pdf': f'https://www.sciopen.com/local/article_pdf/{doi}.pdf',
            'publisher': '清华大学出版社',
            'issn': '2096-0654',
            'publication_date': details['publication_date'],
            'online_date': details['online_date'],
            'received': details['received'],
            'revised': details['revised'],
            'accepted': details['accepted'],
            'published': details['published'],
            'internal_id': details['internal_id'],
        }
        results.append(article_obj)
        time.sleep(0.5)

    # Load existing articles
    with open('articles_md/articles.json', 'r', encoding='utf-8') as f:
        existing = json.load(f)

    print(f"\nExisting articles: {len(existing)}")
    print(f"New articles: {len(results)}")

    # Merge by DOI
    existing_dois = {a['doi'] for a in existing}
    new_articles = [a for a in results if a['doi'] not in existing_dois]
    all_articles = existing + new_articles

    print(f"After merge: {len(all_articles)} articles")

    # Sort: volume desc, issue desc, firstpage desc
    all_articles.sort(key=lambda a: (-int(a.get('volume') or 0), -int(a.get('issue') or 0), -int(a.get('firstpage') or 0)))

    with open('articles_md/articles.json', 'w', encoding='utf-8') as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print("Done! Saved to articles_md/articles.json")

if __name__ == '__main__':
    main()
