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

class ComprehensiveArticleScraper:
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
            # Add random delay to avoid being blocked
            time.sleep(random.uniform(*self.delay_range))
            
            response = self.session.get(url, timeout=20)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.RequestException as e:
            print(f"❌ Error fetching {url}: {str(e)}")
            return None
    
    def extract_date(self, block, fallback_date="No Date"):
        """Extract date from various possible locations"""
        date_selectors = [
            'time[datetime]', 'time',
            '.date', '.publish-date', '.post-date', '.article-date',
            '.meta-date', '.entry-date', '.published', '.timestamp',
            '[datetime]', '[data-date]', '.time', '.pub-time',
            '.article-time', '.news-time', '.post-time'
        ]
        
        for selector in date_selectors:
            date_elem = block.select_one(selector)
            if date_elem:
                # Try to get datetime attribute first
                date_text = (date_elem.get('datetime') or 
                           date_elem.get('data-date') or 
                           date_elem.get('title') or
                           date_elem.get_text(strip=True))
                if date_text and date_text.strip() and date_text != "No Date":
                    normalized = self.normalize_date(date_text)
                    if normalized != date_text:  # Successfully normalized
                        return normalized
        
        # Try to find date in parent elements
        parent = block.parent if block.parent else block
        for selector in date_selectors:
            date_elem = parent.select_one(selector)
            if date_elem:
                date_text = (date_elem.get('datetime') or 
                           date_elem.get('data-date') or 
                           date_elem.get_text(strip=True))
                if date_text and date_text.strip():
                    normalized = self.normalize_date(date_text)
                    if normalized != date_text:
                        return normalized
        
        return fallback_date
    
    def normalize_date(self, date_str):
        """Normalize date format"""
        try:
            # Clean the date string
            date_str = re.sub(r'^(published|posted|on|updated)\s*:?\s*', '', date_str.strip(), flags=re.IGNORECASE)
            date_str = re.sub(r'\s+', ' ', date_str)  # Remove extra spaces
            
            # Try to parse various date formats
            date_patterns = [
                '%Y-%m-%dT%H:%M:%S.%fZ',
                '%Y-%m-%dT%H:%M:%SZ',
                '%Y-%m-%dT%H:%M:%S',
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
            
            for pattern in date_patterns:
                try:
                    # Extract only the part that matches the pattern length
                    test_str = date_str[:len(pattern.replace('%f', '000000'))]
                    parsed_date = datetime.strptime(test_str, pattern)
                    return parsed_date.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            
            # Try regex patterns for common formats
            regex_patterns = [
                (r'(\d{4})-(\d{1,2})-(\d{1,2})', lambda m: f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"),
                (r'(\d{1,2})/(\d{1,2})/(\d{4})', lambda m: f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}"),
                (r'(\d{1,2})-(\d{1,2})-(\d{4})', lambda m: f"{m.group(3)}-{m.group(1).zfill(2)}-{m.group(2).zfill(2)}")
            ]
            
            for pattern, formatter in regex_patterns:
                match = re.search(pattern, date_str)
                if match:
                    return formatter(match)
                    
            return date_str  # Return original if can't parse
        except Exception:
            return date_str
    
    def extract_article_data(self, block, base_url, section_name=""):
        """Extract article data from a block element"""
        # Title extraction with multiple fallbacks
        title_selectors = [
            'h1', 'h2', 'h3', 'h4', 'h5',
            '.title', '.headline', '.post-title', '.article-title',
            '.entry-title', '.news-title', '.story-title',
            'a[title]', '.link-title'
        ]
        
        title = "No Title"
        link = base_url
        
        for selector in title_selectors:
            title_elem = block.select_one(selector)
            if title_elem:
                # Get title text
                title_text = title_elem.get('title') or title_elem.get_text(strip=True)
                if title_text and len(title_text.strip()) > 3:
                    title = title_text.strip()
                    
                    # Try to find link in title element or its children
                    link_elem = title_elem if title_elem.name == 'a' else title_elem.find('a')
                    if link_elem and link_elem.get('href'):
                        link = urljoin(base_url, link_elem['href'])
                    break
        
        # If no link found in title, look for other link patterns
        if link == base_url:
            link_selectors = [
                'a[href]',
                '.read-more a', '.continue-reading a', '.view-more a',
                '.post-link', '.article-link', '.news-link',
                '.story-link', '.permalink'
            ]
            for selector in link_selectors:
                link_elem = block.select_one(selector)
                if link_elem and link_elem.get('href'):
                    href = link_elem['href']
                    if href and not href.startswith('#') and not href.startswith('javascript'):
                        link = urljoin(base_url, href)
                        break
        
        # Date extraction
        date = self.extract_date(block)
        
        # Description extraction
        desc_selectors = [
            '.excerpt', '.summary', '.description', '.post-excerpt',
            '.article-summary', '.entry-summary', '.story-summary',
            '.news-summary', '.abstract', '.lead', '.snippet',
            'p', '.content p'
        ]
        
        description = "No Description"
        for selector in desc_selectors:
            desc_elem = block.select_one(selector)
            if desc_elem:
                desc_text = desc_elem.get_text(strip=True)
                # Filter out very short or navigation-like text
                if desc_text and len(desc_text) > 20 and not any(nav_word in desc_text.lower() for nav_word in ['read more', 'continue reading', 'view more', 'click here']):
                    description = desc_text[:500]  # Limit description length
                    break
        
        return {
            'date': date,
            'url': link,
            'title': title,
            'description': description,
            'section': section_name
        }
    
    def find_articles_on_page(self, soup, base_url, section_name=""):
        """Find all articles on a page using multiple strategies"""
        articles = []
        
        # For main pages, be more aggressive in finding articles
        is_main_page = section_name in ["Main Page", ""]
        
        if is_main_page:
            print(f"  🏠 Scanning main page for ALL article sections...")
            
            # Strategy for main page: Look for section containers first
            section_containers = soup.find_all(['div', 'section'], class_=re.compile(r'(news|article|story|content|main|home|feed)', re.I))
            if not section_containers:
                section_containers = soup.find_all(['div', 'section'], id=re.compile(r'(news|article|story|content|main|home|feed)', re.I))
            
            print(f"    🔍 Found {len(section_containers)} potential section containers")
            
            # Look for articles in each container
            for container in section_containers:
                container_articles = self.extract_articles_from_container(container, base_url, section_name)
                articles.extend(container_articles)
        
        # Strategy 1: Look for article tags
        article_blocks = soup.find_all('article')
        
        # Strategy 2: Look for common article containers with expanded selectors for main page
        if not article_blocks or is_main_page:
            container_selectors = [
                'article', '.post', '.article', '.news-item', '.blog-post', '.story',
                '.entry', '.news-card', '.article-card', '.story-card',
                '.post-item', '.content-item', '.news-list-item', '.feed-item',
                '[class*="post"]', '[class*="article"]', '[class*="news"]',
                '[class*="story"]', '[class*="item"]', '[class*="card"]',
                '.item', '.list-item', '.media', '.media-object'
            ]
            
            all_blocks = []
            for selector in container_selectors:
                found_blocks = soup.select(selector)
                if found_blocks:
                    all_blocks.extend(found_blocks)
                    if is_main_page:
                        print(f"    📋 Found {len(found_blocks)} blocks using selector: {selector}")
            
            # Remove duplicates while preserving order
            seen = set()
            article_blocks = []
            for block in all_blocks:
                if id(block) not in seen:
                    article_blocks.append(block)
                    seen.add(id(block))
        
        # Strategy 3: Look for list items that might contain articles
        if not article_blocks or is_main_page:
            list_selectors = ['li', '.list-item', '.item', 'tr']
            for selector in list_selectors:
                potential_blocks = soup.select(selector)
                valid_blocks = []
                for block in potential_blocks:
                    if (block.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']) and 
                        block.find('a') and 
                        len(block.get_text(strip=True)) > 30):
                        valid_blocks.append(block)
                
                if valid_blocks:
                    article_blocks.extend(valid_blocks)
                    if is_main_page:
                        print(f"    📋 Found {len(valid_blocks)} list items with articles")
        
        # Strategy 4: Aggressive search for main page - any div with title and link
        if is_main_page:
            print(f"    🔍 Performing aggressive search for missed articles...")
            potential_articles = soup.find_all('div')
            additional_blocks = []
            for div in potential_articles:
                # Check if div has heading and link and meaningful content
                if (div.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']) and 
                    div.find('a', href=True) and 
                    len(div.get_text(strip=True)) > 40):
                    
                    # Avoid duplicates
                    if div not in article_blocks:
                        additional_blocks.append(div)
            
            article_blocks.extend(additional_blocks)
            print(f"    📋 Found {len(additional_blocks)} additional article blocks")
        
        print(f"  📰 Total potential article blocks found: {len(article_blocks)}")
        
        # Extract data from all found blocks
        for i, block in enumerate(article_blocks):
            try:
                article_data = self.extract_article_data(block, base_url, section_name)
                
                # Only add if we found meaningful title and it's not a duplicate
                if (article_data['title'] != "No Title" and 
                    len(article_data['title']) > 5 and 
                    article_data['url'] not in self.visited_urls and
                    not any(skip_word in article_data['title'].lower() for skip_word in ['menu', 'navigation', 'search', 'login'])):
                    
                    articles.append(article_data)
                    self.visited_urls.add(article_data['url'])
                    print(f"    ✅ [{i+1}] {article_data['title'][:70]}...")
                    
            except Exception as e:
                print(f"    ❌ Error extracting article {i+1}: {str(e)}")
                continue
        
        return articles
    
    def extract_articles_from_container(self, container, base_url, section_name):
        """Extract articles from a specific container/section"""
        articles = []
        
        # Look for article elements within the container
        article_elements = container.find_all(['article', 'div', 'li'], class_=re.compile(r'(item|card|post|article|news|story)', re.I))
        
        if not article_elements:
            # Fallback: look for any element with heading and link
            article_elements = container.find_all(['div', 'li'])
            article_elements = [elem for elem in article_elements if elem.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']) and elem.find('a')]
        
        for element in article_elements:
            try:
                article_data = self.extract_article_data(element, base_url, section_name)
                if (article_data['title'] != "No Title" and 
                    len(article_data['title']) > 5 and 
                    article_data['url'] not in self.visited_urls):
                    articles.append(article_data)
                    self.visited_urls.add(article_data['url'])
            except:
                continue
        
        return articles
    
    def find_load_more_buttons(self, soup, current_url):
        """Find 'Load More', 'View More', or similar buttons/links"""
        load_more_selectors = [
            'a[class*="load"]', 'a[class*="more"]', 'a[class*="show"]',
            'button[class*="load"]', 'button[class*="more"]', 'button[class*="show"]',
            '.load-more', '.view-more', '.show-more', '.read-more',
            '.pagination-next', '.next-page', 'a[rel="next"]'
        ]
        
        for selector in load_more_selectors:
            load_elem = soup.select_one(selector)
            if load_elem:
                if load_elem.name == 'a' and load_elem.get('href'):
                    href = load_elem['href']
                    if not href.startswith('#') and not href.startswith('javascript'):
                        return urljoin(current_url, href)
                elif load_elem.get('data-url'):
                    return urljoin(current_url, load_elem['data-url'])
        
        # Look for text-based "more" links
        for link in soup.find_all('a', href=True):
            link_text = link.get_text(strip=True).lower()
            if any(phrase in link_text for phrase in ['view more', 'load more', 'show more', 'see more', 'more news', 'next page', 'continue']):
                href = link['href']
                if not href.startswith('#') and not href.startswith('javascript'):
                    return urljoin(current_url, href)
        
        return None
    
    def find_section_urls(self, soup, base_url):
        """Find all section URLs from navigation menu"""
        section_data = {}  # Dictionary to store URL -> section name mapping
        
        print("🔍 Looking for navigation sections...")
        
        # Look for navigation menus with priority order
        nav_selectors = [
            'nav', '.navigation', '.nav', '.menu', '.navbar',
            '.main-nav', '.primary-nav', '.header-nav',
            '.nav-menu', '.menu-list', '.nav-list',
            '.top-nav', '.site-nav', '.global-nav'
        ]
        
        nav_elements = []
        for selector in nav_selectors:
            found_navs = soup.select(selector)
            if found_navs:
                nav_elements.extend(found_navs)
                print(f"  📋 Found navigation using selector: {selector}")
        
        # Also look in header areas
        header_selectors = ['header', '.header', '.site-header', '.main-header']
        for selector in header_selectors:
            header_elements = soup.select(selector)
            for header in header_elements:
                nav_in_header = header.find_all('a', href=True)
                if nav_in_header:
                    nav_elements.append(header)
                    print(f"  📋 Found navigation links in: {selector}")
        
        # If still no nav found, look for any links that might be sections
        if not nav_elements:
            print("  ⚠️ No specific navigation found, scanning entire page...")
            nav_elements = [soup]  # Use entire document
        
        section_keywords = [
            'news', 'world', 'business', 'politics', 'sports', 'tech', 'technology',
            'science', 'health', 'entertainment', 'lifestyle', 'culture',
            'economy', 'finance', 'international', 'domestic', 'local',
            'breaking', 'latest', 'trending', 'opinion', 'analysis',
            'china', 'asia', 'europe', 'america', 'africa', 'global',
            'society', 'travel', 'food', 'auto', 'education', 'military'
        ]
        
        avoid_keywords = [
            'contact', 'about', 'login', 'register', 'search', 'archive',
            'subscribe', 'newsletter', 'rss', 'sitemap', 'privacy', 'terms',
            'careers', 'jobs', 'advertise', 'feedback', 'help', 'support'
        ]
        
        for nav_elem in nav_elements:
            links = nav_elem.find_all('a', href=True)
            print(f"  🔗 Checking {len(links)} links in navigation...")
            
            for link in links:
                href = link.get('href', '').strip()
                link_text = link.get_text(strip=True)
                
                # Skip empty or invalid links
                if not href or href.startswith('#') or href.startswith('javascript') or href.startswith('mailto'):
                    continue
                
                # Create full URL
                full_url = urljoin(base_url, href)
                
                # Skip if same as base URL
                if full_url == base_url or full_url == base_url + '/':
                    continue
                
                # Clean link text
                clean_text = link_text.lower().strip()
                clean_href = href.lower()
                
                # Check if it's likely a section URL
                is_section = False
                section_name = link_text.strip()
                
                # Method 1: Check if link text contains section keywords
                if any(keyword in clean_text for keyword in section_keywords):
                    is_section = True
                    print(f"    ✅ Found by text keyword: '{link_text}' -> {full_url}")
                
                # Method 2: Check if URL path contains section keywords  
                elif any(keyword in clean_href for keyword in section_keywords):
                    is_section = True
                    # Extract section name from URL if text is generic
                    if len(clean_text) < 3 or clean_text in ['more', 'all', 'view']:
                        section_name = href.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
                    print(f"    ✅ Found by URL keyword: '{section_name}' -> {full_url}")
                
                # Method 3: Short navigation text (likely sections)
                elif len(link_text.split()) <= 2 and len(link_text) > 2 and link_text.isalpha():
                    is_section = True
                    print(f"    ✅ Found by short text: '{link_text}' -> {full_url}")
                
                # Method 4: Check URL structure (common section patterns)
                elif any(pattern in clean_href for pattern in ['/news/', '/category/', '/section/']):
                    is_section = True
                    section_name = href.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
                    print(f"    ✅ Found by URL pattern: '{section_name}' -> {full_url}")
                
                # Skip if contains avoid keywords
                if any(avoid in clean_text or avoid in clean_href for avoid in avoid_keywords):
                    is_section = False
                
                if is_section:
                    # Clean up section name
                    if not section_name or section_name.lower() in ['more', 'all', 'view', 'news']:
                        section_name = href.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
                    
                    section_data[full_url] = section_name
        
        print(f"  🎯 Total sections discovered: {len(section_data)}")
        for url, name in section_data.items():
            print(f"    📂 {name}: {url}")
        
        return section_data
    
    def scrape_section_completely(self, section_url, section_name="", max_pages=50):
        """Scrape all articles from a section by following 'View More' links"""
        print(f"\n🏷️  Scraping section: {section_name or section_url}")
        section_articles = []
        current_url = section_url
        page_count = 0
        section_visited = set()
        
        while current_url and page_count < max_pages:
            if current_url in section_visited:
                print(f"    🔄 Loop detected, stopping...")
                break
            
            section_visited.add(current_url)
            print(f"    📄 Page {page_count + 1}: {current_url}")
            
            soup = self.get_page_content(current_url)
            if not soup:
                print(f"    ❌ Failed to load page")
                break
            
            # Extract articles from current page
            page_articles = self.find_articles_on_page(soup, current_url, section_name)
            
            if page_articles:
                section_articles.extend(page_articles)
                print(f"    ✅ Found {len(page_articles)} articles on this page")
            else:
                print(f"    ⚠️  No articles found on this page")
            
            # Find next page / load more
            next_url = self.find_load_more_buttons(soup, current_url)
            if next_url and next_url != current_url:
                current_url = next_url
                page_count += 1
            else:
                print(f"    🏁 No more pages found")
                break
        
        print(f"  📊 Section total: {len(section_articles)} articles")
        return section_articles
    
    def scrape_all_news_comprehensive(self, start_url, max_sections=20):
        """Comprehensively scrape all news from all sections of a website"""
        print(f"🚀 Starting comprehensive news scraping from: {start_url}")
        print("=" * 80)
        
        # Step 1: Get main page and find all section URLs
        print("🔍 Step 1: Finding all news sections...")
        soup = self.get_page_content(start_url)
        if not soup:
            print("❌ Failed to load main page")
            return []
        
        # Extract articles from main page first
        print("\n📰 STEP 1A: Comprehensive main page article extraction...")
        print("🔍 Scanning for ALL articles on homepage (Home, China, World, etc.)")
        main_articles = self.find_articles_on_page(soup, start_url, "Main Page")
        print(f"✅ Found {len(main_articles)} articles on main page")
        self.all_articles.extend(main_articles)
        
        # Find all section URLs with names
        print(f"\n📰 STEP 1B: Finding navigation sections...")
        section_data = self.find_section_urls(soup, start_url)
        print(f"✅ Found {len(section_data)} sections to scrape")
        
        # Step 2: Scrape each section completely
        print(f"\n🔄 STEP 2: Scraping each section comprehensively...")
        print("=" * 60)
        
        section_items = list(section_data.items())[:max_sections]
        
        for i, (section_url, section_name) in enumerate(section_items, 1):
            try:
                print(f"\n[{i}/{len(section_items)}] Processing section: {section_name}")
                print(f"    🔗 URL: {section_url}")
                
                section_articles = self.scrape_section_completely(section_url, section_name)
                self.all_articles.extend(section_articles)
                
            except Exception as e:
                print(f"❌ Error scraping section {section_name} ({section_url}): {str(e)}")
                continue
        
        # Remove duplicates
        unique_articles = []
        seen_urls = set()
        
        for article in self.all_articles:
            if article['url'] not in seen_urls:
                unique_articles.append(article)
                seen_urls.add(article['url'])
        
        print(f"\n🎉 Comprehensive scraping completed!")
        print(f"📊 Total unique articles found: {len(unique_articles)}")
        print(f"🗂️  Sections processed: {len(set(article.get('section', '') for article in unique_articles))}")
        
        return unique_articles

def save_to_csv(data, filename):
    """Save article data to CSV file with section information"""
    try:
        os.makedirs(data_path, exist_ok=True)
        full_path = os.path.join(data_path, filename)
        
        with open(full_path, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["date", "url", "title", "description", "section"])
            
            for article in data:
                writer.writerow([
                    article['date'],
                    article['url'], 
                    article['title'],
                    article['description'],
                    article.get('section', '')
                ])
        
        print(f"\n✅ Data successfully saved to: {full_path}")
        return full_path
        
    except Exception as e:
        print(f"❌ Error saving to CSV: {str(e)}")
        return None

def main():
    print("🌍 Comprehensive News Website Scraper")
    print("=" * 60)
    print("This scraper will:")
    print("• Find all news sections on the website")
    print("• Visit each section and scrape ALL articles")
    print("• Follow 'View More' / 'Load More' links")
    print("• Get current and previous articles")
    print("=" * 60)
    
    # Get user input
    start_url = input("\n🔗 Enter the news website URL (e.g., https://www.cgtn.com): ").strip()
    
    if not start_url:
        print("❌ No URL provided!")
        return
    
    # Add protocol if missing
    if not start_url.startswith(('http://', 'https://')):
        start_url = 'https://' + start_url
    
    filename = input("💾 Enter filename to save (default: comprehensive_news.csv): ").strip()
    if not filename:
        filename = "comprehensive_news.csv"
    elif not filename.endswith('.csv'):
        filename += ".csv"
    
    # Ask for max sections
    max_sections_input = input("🔢 Maximum sections to scrape (default: 20): ").strip()
    max_sections = 20
    if max_sections_input:
        try:
            max_sections = int(max_sections_input)
        except ValueError:
            print("Invalid number, using default: 20")
    
    # Initialize scraper and start comprehensive scraping
    scraper = ComprehensiveArticleScraper(delay_range=(2, 4))  # Slightly longer delays
    
    try:
        articles = scraper.scrape_all_news_comprehensive(start_url, max_sections)
        
        if articles:
            print(f"\n📈 Final Results:")
            print(f"   📰 Total articles: {len(articles)}")
            
            # Show section breakdown
            sections = {}
            for article in articles:
                section = article.get('section', 'Unknown')
                sections[section] = sections.get(section, 0) + 1
            
            print(f"   🗂️  Sections found: {len(sections)}")
            for section, count in sorted(sections.items(), key=lambda x: x[1], reverse=True):
                print(f"      • {section}: {count} articles")
            
            # Save to CSV
            saved_path = save_to_csv(articles, filename)
            
            if saved_path:
                print(f"\n🎯 Success! Comprehensive news data saved to:")
                print(f"   📁 {saved_path}")
            
        else:
            print("⚠️ No articles were found. Possible reasons:")
            print("  • Website structure not supported")
            print("  • Website blocks automated scraping")
            print("  • Network connectivity issues")
            print("  • URL doesn't contain news sections")
            
    except KeyboardInterrupt:
        print("\n\n⏹️ Scraping interrupted by user")
        if scraper.all_articles:
            print(f"💾 Saving {len(scraper.all_articles)} articles collected so far...")
            save_to_csv(scraper.all_articles, f"partial_{filename}")
    except Exception as e:
        print(f"\n❌ An error occurred: {str(e)}")
        if scraper.all_articles:
            print(f"💾 Saving {len(scraper.all_articles)} articles collected so far...")
            save_to_csv(scraper.all_articles, f"partial_{filename}")

if __name__ == "__main__":
    main()