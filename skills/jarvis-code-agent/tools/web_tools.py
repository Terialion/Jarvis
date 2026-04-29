"""
网页工具 - 访问外部网站并提取信息
提供网页访问、信息提取、内容搜索等功能
"""

import re
import json
import urllib.request
import urllib.error
import urllib.parse
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime
from html.parser import HTMLParser
from colorama import Fore, Style


@dataclass
class WebPage:
    """网页数据类"""
    url: str
    title: str
    content: str
    links: List[str]
    headers: Dict[str, str]
    status_code: int
    fetch_time: datetime


class HTMLTextExtractor(HTMLParser):
    """HTML 文本提取器"""
    
    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.in_script = False
        self.in_style = False
        self.skip_tags = {'script', 'style', 'nav', 'footer', 'header', 'aside'}
        self.current_tag = None
        
    def handle_starttag(self, tag, attrs):
        self.current_tag = tag
        if tag in self.skip_tags:
            if tag == 'script':
                self.in_script = True
            elif tag == 'style':
                self.in_style = True
        elif tag == 'br':
            self.text_parts.append('\n')
        elif tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li'):
            self.text_parts.append('\n')
            
    def handle_endtag(self, tag):
        if tag == 'script':
            self.in_script = False
        elif tag == 'style':
            self.in_style = False
        elif tag in ('p', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr'):
            self.text_parts.append('\n')
            
    def handle_data(self, data):
        if not self.in_script and not self.in_style:
            # 清理空白字符
            text = ' '.join(data.split())
            if text:
                self.text_parts.append(text)
                
    def get_text(self) -> str:
        """获取提取的文本"""
        text = ' '.join(self.text_parts)
        # 清理多余空白
        text = re.sub(r'\n\s*\n', '\n\n', text)
        text = re.sub(r' +', ' ', text)
        return text.strip()


def fetch_webpage(url: str, timeout: int = 30, headers: Optional[Dict] = None) -> WebPage:
    """
    获取网页内容
    
    Args:
        url: 网页 URL
        timeout: 超时时间（秒）
        headers: 自定义请求头
        
    Returns:
        WebPage 对象
    """
    # 确保 URL 格式正确
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    # 默认请求头
    default_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'identity',
        'Connection': 'keep-alive',
    }
    
    if headers:
        default_headers.update(headers)
    
    try:
        req = urllib.request.Request(url, headers=default_headers)
        
        print(f"{Fore.CYAN}[网络] 正在获取: {url}{Style.RESET_ALL}")
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            # 获取响应信息
            status_code = response.getcode()
            response_headers = dict(response.headers)
            
            # 读取内容
            content_bytes = response.read()
            
            # 尝试解码
            charset = 'utf-8'
            content_type = response_headers.get('Content-Type', '')
            if 'charset=' in content_type:
                charset = content_type.split('charset=')[-1].split(';')[0].strip()
            
            try:
                html_content = content_bytes.decode(charset, errors='replace')
            except:
                html_content = content_bytes.decode('utf-8', errors='replace')
            
            # 提取标题
            title_match = re.search(r'<title[^>]*>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
            title = title_match.group(1).strip() if title_match else '无标题'
            title = re.sub(r'<[^>]+>', '', title)  # 移除标签
            
            # 提取链接
            links = re.findall(r'href=["\'](https?://[^"\']+)["\']', html_content)
            
            # 提取正文
            extractor = HTMLTextExtractor()
            try:
                extractor.feed(html_content)
                content = extractor.get_text()
            except:
                # 如果解析失败，使用简单正则
                content = re.sub(r'<[^>]+>', ' ', html_content)
                content = re.sub(r'\s+', ' ', content).strip()
            
            print(f"{Fore.GREEN}[网络] 获取成功: {title[:50]}{Style.RESET_ALL}")
            
            return WebPage(
                url=url,
                title=title,
                content=content,
                links=links[:20],  # 限制链接数量
                headers=dict(response_headers),
                status_code=status_code,
                fetch_time=datetime.now()
            )
            
    except urllib.error.HTTPError as e:
        raise Exception(f"HTTP 错误 {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise Exception(f"URL 错误: {e.reason}")
    except TimeoutError:
        raise Exception(f"请求超时（{timeout}秒）")
    except Exception as e:
        raise Exception(f"获取失败: {str(e)}")


def extract_key_info(content: str, max_length: int = 2000, keywords: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    从网页内容中提取关键信息
    
    Args:
        content: 网页文本内容
        max_length: 最大返回长度
        keywords: 关注的关键词列表
        
    Returns:
        提取的信息字典
    """
    # 分段
    paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
    
    # 提取关键段落
    key_paragraphs = []
    for para in paragraphs[:20]:  # 限制段落数量
        if len(para) > 50:  # 过滤短段落
            key_paragraphs.append(para)
    
    # 如果有关键词，进行高亮和相关性排序
    if keywords:
        scored_paragraphs = []
        for para in key_paragraphs:
            score = sum(1 for kw in keywords if kw.lower() in para.lower())
            scored_paragraphs.append((score, para))
        
        scored_paragraphs.sort(reverse=True)
        key_paragraphs = [p for _, p in scored_paragraphs[:10]]
    
    # 提取可能的代码块
    code_blocks = re.findall(r'```[\s\S]*?```', content)
    if not code_blocks:
        # 尝试识别缩进代码
        code_blocks = re.findall(r'(?:^|\n)(    [^\n]+\n)+', content)
    
    # 提取列表项
    list_items = re.findall(r'^[\s]*[-*•][\s]+(.+)$', content, re.MULTILINE)
    
    # 提取可能的标题
    headings = re.findall(r'^[\s]*#{1,6}[\s]+(.+)$', content, re.MULTILINE)
    if not headings:
        headings = re.findall(r'^[\s]*([A-Z][A-Za-z\s]{3,50})[\s]*$', content, re.MULTILINE)
    
    # 构建结果
    result = {
        "summary": '\n\n'.join(key_paragraphs[:5])[:max_length],
        "paragraphs_count": len(paragraphs),
        "key_paragraphs": key_paragraphs[:5],
        "code_blocks": code_blocks[:3],
        "list_items": list_items[:10],
        "headings": headings[:10],
        "total_length": len(content)
    }
    
    return result


def search_web(query: str, num_results: int = 5) -> List[Dict[str, str]]:
    """
    搜索网页（使用 DuckDuckGo Lite 或类似服务）
    
    Args:
        query: 搜索关键词
        num_results: 返回结果数量
        
    Returns:
        搜索结果列表
    """
    # 使用 DuckDuckGo HTML 版本
    search_url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    
    try:
        print(f"{Fore.CYAN}[搜索] 搜索: {query}{Style.RESET_ALL}")
        
        page = fetch_webpage(search_url, timeout=15)
        
        # 解析搜索结果
        results = []
        
        # 尝试提取搜索结果
        # DuckDuckGo 结果格式
        result_blocks = re.findall(
            r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?<a[^>]*class="result__snippet"[^>]*>(.*?)</a>',
            page.content,
            re.DOTALL | re.IGNORECASE
        )
        
        for url, title, snippet in result_blocks[:num_results]:
            # 清理 HTML 标签
            title = re.sub(r'<[^>]+>', '', title)
            snippet = re.sub(r'<[^>]+>', '', snippet)
            
            results.append({
                "title": title.strip(),
                "url": url.strip(),
                "snippet": snippet.strip()[:200]
            })
        
        # 如果上面的模式不匹配，尝试备用模式
        if not results:
            links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>([^<]+)</a>', page.content)
            for url, title in links[:num_results]:
                if url.startswith('http') and len(title.strip()) > 10:
                    results.append({
                        "title": title.strip(),
                        "url": url.strip(),
                        "snippet": ""
                    })
        
        print(f"{Fore.GREEN}[搜索] 找到 {len(results)} 个结果{Style.RESET_ALL}")
        
        return results
        
    except Exception as e:
        print(f"{Fore.YELLOW}[搜索] 搜索失败: {e}{Style.RESET_ALL}")
        return []


def fetch_and_summarize(url: str, max_length: int = 1000) -> Dict[str, Any]:
    """
    获取网页并生成摘要
    
    Args:
        url: 网页 URL
        max_length: 摘要最大长度
        
    Returns:
        包含摘要的字典
    """
    try:
        page = fetch_webpage(url)
        
        # 提取关键信息
        info = extract_key_info(page.content, max_length=max_length)
        
        return {
            "success": True,
            "url": page.url,
            "title": page.title,
            "summary": info["summary"],
            "headings": info["headings"],
            "fetch_time": page.fetch_time.isoformat(),
            "status_code": page.status_code
        }
        
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "error": str(e)
        }


def search_and_fetch(query: str, num_results: int = 3, fetch_content: bool = True) -> Dict[str, Any]:
    """
    搜索并获取内容
    
    Args:
        query: 搜索关键词
        num_results: 搜索结果数量
        fetch_content: 是否获取详细内容
        
    Returns:
        搜索结果和内容的字典
    """
    # 执行搜索
    search_results = search_web(query, num_results)
    
    if not search_results:
        return {
            "success": False,
            "query": query,
            "error": "未找到搜索结果"
        }
    
    result = {
        "success": True,
        "query": query,
        "results_count": len(search_results),
        "results": search_results
    }
    
    # 获取详细内容
    if fetch_content:
        detailed_results = []
        
        for item in search_results[:2]:  # 只获取前2个的详细内容
            try:
                summary = fetch_and_summarize(item["url"], max_length=800)
                detailed_results.append({
                    "search_result": item,
                    "content": summary
                })
            except Exception as e:
                detailed_results.append({
                    "search_result": item,
                    "error": str(e)
                })
        
        result["detailed_results"] = detailed_results
    
    return result


def extract_code_from_webpage(url: str, language: Optional[str] = None) -> Dict[str, Any]:
    """
    从网页提取代码示例
    
    Args:
        url: 网页 URL
        language: 代码语言过滤
        
    Returns:
        提取的代码
    """
    try:
        page = fetch_webpage(url)
        
        # 提取代码块
        code_blocks = []
        
        # Markdown 代码块
        md_blocks = re.findall(r'```(\w+)?\n(.*?)```', page.content, re.DOTALL)
        for lang, code in md_blocks:
            if not language or (lang and language.lower() in lang.lower()):
                code_blocks.append({
                    "language": lang or "unknown",
                    "code": code.strip()
                })
        
        # HTML pre/code 标签
        html_blocks = re.findall(r'<pre[^>]*>(.*?)</pre>', page.content, re.DOTALL | re.IGNORECASE)
        for block in html_blocks:
            code = re.sub(r'<[^>]+>', '', block)
            if len(code.strip()) > 50:
                code_blocks.append({
                    "language": language or "unknown",
                    "code": code.strip()
                })
        
        return {
            "success": True,
            "url": url,
            "title": page.title,
            "code_blocks": code_blocks[:10],
            "total_found": len(code_blocks)
        }
        
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "error": str(e)
        }


def format_webpage_info(page: WebPage, max_content_length: int = 500) -> str:
    """
    格式化网页信息为字符串
    
    Args:
        page: WebPage 对象
        max_content_length: 内容最大长度
        
    Returns:
        格式化字符串
    """
    lines = [
        f"{Fore.CYAN}╔════════════════════════════════════════╗{Style.RESET_ALL}",
        f"{Fore.CYAN}║{Style.RESET_ALL} {Fore.YELLOW}[网页信息]{Style.RESET_ALL}".ljust(43) + f"{Fore.CYAN}║{Style.RESET_ALL}",
        f"{Fore.CYAN}╠════════════════════════════════════════╣{Style.RESET_ALL}",
        f"标题: {page.title}",
        f"URL: {page.url}",
        f"状态: {page.status_code}",
        f"获取时间: {page.fetch_time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "内容预览:",
        "-" * 40,
    ]
    
    content = page.content[:max_content_length]
    if len(page.content) > max_content_length:
        content += "..."
    
    lines.append(content)
    
    if page.links:
        lines.extend([
            "",
            f"相关链接 ({len(page.links)}个):",
            "-" * 40
        ])
        for link in page.links[:5]:
            lines.append(f"  - {link}")
    
    lines.append(f"{Fore.CYAN}╚════════════════════════════════════════╝{Style.RESET_ALL}")
    
    return "\n".join(lines)


def format_search_results(results: List[Dict[str, str]]) -> str:
    """
    格式化搜索结果
    
    Args:
        results: 搜索结果列表
        
    Returns:
        格式化字符串
    """
    if not results:
        return f"{Fore.YELLOW}未找到搜索结果{Style.RESET_ALL}"
    
    lines = [
        f"{Fore.CYAN}╔════════════════════════════════════════╗{Style.RESET_ALL}",
        f"{Fore.CYAN}║{Style.RESET_ALL} {Fore.YELLOW}[搜索结果]{Style.RESET_ALL}".ljust(43) + f"{Fore.CYAN}║{Style.RESET_ALL}",
        f"{Fore.CYAN}╠════════════════════════════════════════╣{Style.RESET_ALL}",
    ]
    
    for i, result in enumerate(results, 1):
        lines.append(f"\n{i}. {Fore.GREEN}{result.get('title', '无标题')}{Style.RESET_ALL}")
        lines.append(f"   URL: {result.get('url', '')}")
        if result.get('snippet'):
            snippet = result['snippet'][:150]
            if len(result['snippet']) > 150:
                snippet += "..."
            lines.append(f"   摘要: {snippet}")
    
    lines.append(f"\n{Fore.CYAN}╚════════════════════════════════════════╝{Style.RESET_ALL}")
    
    return "\n".join(lines)


# 工具注册表
WEB_TOOLS = {
    "fetch_webpage": fetch_webpage,
    "extract_key_info": extract_key_info,
    "search_web": search_web,
    "fetch_and_summarize": fetch_and_summarize,
    "search_and_fetch": search_and_fetch,
    "extract_code_from_webpage": extract_code_from_webpage,
    "format_webpage_info": format_webpage_info,
    "format_search_results": format_search_results
}
