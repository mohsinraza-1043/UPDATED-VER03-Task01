import requests
from bs4 import BeautifulSoup
import csv
import os
import time
import re
from urllib.parse import urljoin, urlparse
from datetime import datetime
import random

# Save location
data_path = r'D:\INTERNSHIP'

class ImprovedNewsScraper:
    def __init__(self, delay_range=(1, 3)):
        self.delay_range = delay_range
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Cache-Control': 'max-age=0'
        })
        self.all_articles = []
        self.visited_urls = set()
        self.section_urls = set()
    
    def get_page_content(self, url):
        """Fetch page content with error handling and rate limiting"""
        try:
            time.sleep(random.uniform(*self.delay_range))
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.RequestException as e:
            print(f"❌ Error fetching {url}: {str(e)}")
            return None
    
    def extract_date(self, block):
        """Improved date extraction with multiple fallback strategies"""
        date_selectors = [
            ('time[datetime]', lambda el: el.get('datetime')),
            ('time', lambda el: el.get('datetime') or el.get_text()),
            ('[itemprop="datePublished"]', lambda el: el.get('content') or el.get('datetime') or el.get_text()),
            ('.date', lambda el: el.get_text()),
            ('.publish-date', lambda el: el.get_text()),
            ('.post-date', lambda el: el.get_text()),
            ('.article-date', lambda el: el.get_text()),
            ('.timestamp', lambda el: el.get_text()),
            ('[datetime]', lambda el: el.get('datetime')),
            ('[data-date]', lambda el: el.get('data-date')),
            ('.meta-date', lambda el: el.get_text())
        ]
        
        # Try to find date in the block itself
        for selector, extractor in date_selectors:
            date_elem = block.select_one(selector)
            if date_elem:
                date_text = extractor(date_elem)
                if date_text:
                    normalized = self.normalize_date(date_text.strip())
                    if normalized:
                        return normalized
        
        # Check parent elements if not found
        parent = block.parent
        for _ in range(3):  # Check up to 3 parent levels
            if parent:
                for selector, extractor in date_selectors:
                    date_elem = parent.select_one(selector)
                    if date_elem:
                        date_text = extractor(date_elem)
                        if date_text:
                            normalized = self.normalize_date(date_text.strip())
                            if normalized:
                                return normalized
                parent = parent.parent
        
        # Final fallback to current date if nothing found
        return datetime.now().strftime('%m/%d/%Y')
    
    def normalize_date(self, date_str):
        """Normalize various date formats to MM/DD/YYYY"""
        if not date_str:
            return None
            
        # Clean the date string
        date_str = re.sub(r'^(published|posted|on|updated)\s*:?\s*', '', date_str, flags=re.IGNORECASE)
        date_str = re.sub(r'\s+', ' ', date_str.strip())
        
        # Common date patterns
        patterns = [
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d',
            '%B %d, %Y',
            '%b %d, %Y',
            '%d %B %Y',
            '%d %b %Y',
            '%m/%d/%Y',
            '%d/%m/%Y',
            '%Y/%m/%d',
            '%d-%m-%Y',
            '%m-%d-%Y'
        ]
        
        for pattern in patterns:
            try:
                parsed_date = datetime.strptime(date_str[:len(pattern)], pattern)
                return parsed_date.strftime('%m/%d/%Y')
            except ValueError:
                continue
        
        # Try to extract date from text using regex
        date_regex = [
            (r'(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})', lambda m: f"{m.group(1)}/{m.group(2)}/{m.group(3)}"),
            (r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})', lambda m: f"{m.group(2)}/{m.group(3)}/{m.group(1)}")
        ]
        
        for pattern, formatter in date_regex:
            match = re.search(pattern, date_str)
            if match:
                try:
                    return formatter(match)
                except:
                    continue
        
        return None
    
    def extract_description(self, block):
        """Extract article description with better filtering"""
        desc_selectors = [
            '.article-summary', '.entry-summary', '.post-excerpt',
            '.excerpt', '.summary', '.description', 
            '[itemprop="description"]', '.article-content p:first-of-type',
            '.content p:first-of-type', '.lead', '.snippet'
        ]
        
        # Try specific description selectors first
        for selector in desc_selectors:
            desc_elem = block.select_one(selector)
            if desc_elem:
                desc_text = desc_elem.get_text(' ', strip=True)
                if len(desc_text) > 30 and not any(x in desc_text.lower() for x in ['read more', 'continue reading']):
                    return desc_text[:500]  # Limit length
        
        # Fallback to first meaningful paragraph
        for p in block.find_all('p'):
            text = p.get_text(' ', strip=True)
            if len(text) > 50 and not any(x in text.lower() for x in ['read more', 'click here']):
                return text[:500]
        
        return ""
    
    def extract_article_data(self, block, base_url, section_name=""):
        """Extract article data with better filtering"""
        # Skip navigation and non-article blocks
        skip_keywords = ['menu', 'navigation', 'search', 'login', 'sign up', 'subscribe', 'about', 'contact']
        
        # Title extraction
        title = None
        title_elem = (block.find(['h1', 'h2', 'h3']) or 
                     block.select_one('.title, .headline, .post-title, .article-title, .entry-title'))
        
        if title_elem:
            title = title_elem.get_text(strip=True)
            if any(kw in title.lower() for kw in skip_keywords) or len(title) < 5:
                return None
        
        # Link extraction
        link = None
        link_elem = (block.find('a', href=True) or 
                    title_elem.find('a', href=True) if title_elem else None)
        
        if link_elem and link_elem['href'] and not link_elem['href'].startswith(('javascript:', '#')):
            link = urljoin(base_url, link_elem['href'])
        
        if not link or link == base_url:
            return None
        
        # Skip if already visited
        if link in self.visited_urls:
            return None
        
        # Date extraction
        date = self.extract_date(block)
        
        # Description extraction
        description = self.extract_description(block)
        
        # Skip if no meaningful content
        if not title or (not description and len(block.get_text(strip=True)) < 100):
            return None
        
        # Clean section name
        if not section_name or section_name.lower() in ['home', 'main']:
            section_name = "Main"
        
        return {
            'date': date,
            'url': link,
            'title': title,
            'description': description,
            'section': section_name
        }
    
    def find_articles_on_page(self, soup, base_url, section_name=""):
        """Find all articles on a page with better filtering"""
        articles = []
        
        # Look for standard article containers
        article_blocks = soup.find_all(['article', 'div'], class_=re.compile(r'(article|post|news|story|item|card)', re.I))
        
        # Fallback to any block with heading and link
        if len(article_blocks) < 5:
            potential_blocks = soup.find_all(['div', 'li'])
            article_blocks.extend([
                b for b in potential_blocks 
                if b.find(['h1', 'h2', 'h3']) and b.find('a', href=True)
                and len(b.get_text(strip=True)) > 50
                and b not in article_blocks
            ])
        
        for block in article_blocks:
            try:
                article_data = self.extract_article_data(block, base_url, section_name)
                if article_data:
                    articles.append(article_data)
                    self.visited_urls.add(article_data['url'])
            except Exception as e:
                print(f"Error extracting article: {str(e)}")
                continue
        
        return articles
    
    def find_section_urls(self, soup, base_url):
        """Find all section URLs with better filtering"""
        section_data = {}
        
        # Section keywords to look for
        section_keywords = [
            'news', 'world', 'business', 'politics', 'sports', 'tech',
            'science', 'health', 'entertainment', 'lifestyle', 'opinion',
            'breaking', 'latest', 'analysis', 'editorial', 'feature',
            'china', 'asia', 'europe', 'america', 'africa', 'global'
        ]
        
        # Keywords to avoid
        avoid_keywords = [
            'contact', 'about', 'login', 'register', 'search', 'archive',
            'subscribe', 'newsletter', 'rss', 'sitemap', 'privacy', 'terms'
        ]
        
        # Look in navigation elements
        nav_elements = soup.select('nav, .navigation, .nav, .menu, .navbar, header, .header')
        if not nav_elements:
            nav_elements = [soup]  # Fallback to entire document
        
        for nav_elem in nav_elements:
            for link in nav_elem.find_all('a', href=True):
                href = link['href'].strip()
                text = link.get_text(strip=True)
                
                # Skip invalid links
                if not href or href.startswith(('#', 'javascript:', 'mailto:')):
                    continue
                
                full_url = urljoin(base_url, href)
                
                # Skip if same as base URL
                if full_url == base_url.rstrip('/') + '/':
                    continue
                
                # Check if it's a section link
                lower_text = text.lower()
                lower_href = href.lower()
                
                is_section = (
                    any(kw in lower_text for kw in section_keywords) or
                    any(kw in lower_href for kw in section_keywords) or
                    any(p in lower_href for p in ['/news/', '/category/', '/section/'])
                )
                
                # Skip non-section links
                if not is_section or any(kw in lower_text or kw in lower_href for kw in avoid_keywords):
                    continue
                
                # Clean section name
                section_name = text.strip()
                if not section_name or len(section_name) < 2:
                    section_name = href.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
                
                section_data[full_url] = section_name
        
        return section_data
    
    def scrape_section_completely(self, section_url, section_name="", max_pages=5):
        """Scrape a section completely with pagination"""
        section_articles = []
        current_url = section_url
        page_count = 0
        
        while current_url and page_count < max_pages:
            soup = self.get_page_content(current_url)
            if not soup:
                break
            
            # Get articles from current page
            page_articles = self.find_articles_on_page(soup, current_url, section_name)
            section_articles.extend(page_articles)
            
            # Find next page
            next_url = None
            next_link = soup.find('a', text=re.compile(r'next|more', re.I))
            if next_link and next_link.get('href'):
                next_url = urljoin(current_url, next_link['href'])
            
            if not next_url or next_url == current_url:
                break
            
            current_url = next_url
            page_count += 1
        
        return section_articles
    
    def scrape_all_news(self, start_url, max_sections=20):
        """Main scraping function"""
        print(f"🚀 Starting scraping from: {start_url}")
        
        # Get main page
        soup = self.get_page_content(start_url)
        if not soup:
            return []
        
        # Get articles from main page
        main_articles = self.find_articles_on_page(soup, start_url, "Main")
        self.all_articles.extend(main_articles)
        
        # Find sections
        section_data = self.find_section_urls(soup, start_url)
        
        # Scrape each section
        for section_url, section_name in list(section_data.items())[:max_sections]:
            try:
                print(f"Scraping section: {section_name}")
                section_articles = self.scrape_section_completely(section_url, section_name)
                self.all_articles.extend(section_articles)
            except Exception as e:
                print(f"Error scraping section {section_name}: {str(e)}")
                continue
        
        # Remove duplicates
        unique_articles = []
        seen_urls = set()
        for article in self.all_articles:
            if article['url'] not in seen_urls:
                unique_articles.append(article)
                seen_urls.add(article['url'])
        
        return unique_articles

def save_to_csv(data, filename):
    """Save data to CSV with proper formatting"""
    try:
        os.makedirs(data_path, exist_ok=True)
        full_path = os.path.join(data_path, filename)
        
        with open(full_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Date", "Section", "URL", "Title", "Description"])
            
            for article in data:
                writer.writerow([
                    article['date'],
                    article['section'],
                    article['url'],
                    article['title'],
                    article['description']
                ])
        
        print(f"✅ Data saved to: {full_path}")
        return full_path
    except Exception as e:
        print(f"❌ Error saving CSV: {str(e)}")
        return None

def main():
    print("🌍 Improved News Website Scraper")
    print("=" * 60)
    
    # Get user input
    start_url = input("\n🔗 Enter the news website URL: ").strip()
    if not start_url:
        print("❌ No URL provided!")
        return
    
    if not start_url.startswith(('http://', 'https://')):
        start_url = 'https://' + start_url
    
    filename = input("💾 Enter filename to save (default: news_data.csv): ").strip()
    if not filename:
        filename = "news_data.csv"
    elif not filename.endswith('.csv'):
        filename += ".csv"
    
    max_sections = 20
    max_input = input("🔢 Maximum sections to scrape (default: 20): ").strip()
    if max_input:
        try:
            max_sections = int(max_input)
        except ValueError:
            print("⚠️ Invalid number, using default 20")
    
    # Start scraping
    scraper = ImprovedNewsScraper(delay_range=(2, 4))
    
    try:
        articles = scraper.scrape_all_news(start_url, max_sections)
        
        if articles:
            print(f"\n📊 Results:")
            print(f"   Total articles: {len(articles)}")
            
            # Show section breakdown
            sections = {}
            for article in articles:
                section = article.get('section', 'Unknown')
                sections[section] = sections.get(section, 0) + 1
            
            print(f"   Sections found: {len(sections)}")
            for section, count in sorted(sections.items(), key=lambda x: x[1], reverse=True):
                print(f"      • {section}: {count} articles")
            
            # Save to CSV
            saved_path = save_to_csv(articles, filename)
            
            if saved_path:
                print(f"\n✅ Success! Data saved to: {saved_path}")
        else:
            print("⚠️ No articles found. Check website structure or try different URL.")
            
    except KeyboardInterrupt:
        print("\n⏹️ Scraping interrupted by user")
        if scraper.all_articles:
            save_to_csv(scraper.all_articles, f"partial_{filename}")
    except Exception as e:
        print(f"\n❌ Error: {str(e)}")
        if scraper.all_articles:
            save_to_csv(scraper.all_articles, f"partial_{filename}")

if __name__ == "__main__":
    main()
