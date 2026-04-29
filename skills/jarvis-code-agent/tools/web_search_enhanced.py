"""
增强版网页搜索工具 - 为 Jarvis 提供高效的网络搜索能力
支持多种搜索引擎和实时信息获取
"""

import json
import urllib.request
import urllib.error
import urllib.parse
import ssl
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from datetime import datetime
from colorama import Fore, Style


@dataclass
class SearchResult:
    """搜索结果数据类"""
    title: str
    url: str
    snippet: str
    source: str
    timestamp: Optional[str] = None


@dataclass
class TrendingItem:
    """热搜条目"""
    rank: int
    title: str
    url: Optional[str] = None
    heat: Optional[str] = None
    category: Optional[str] = None


class WebSearchEnhanced:
    """
    增强版网络搜索类
    支持多种搜索方式和热搜获取
    """
    
    def __init__(self):
        self.timeout = 15
        self._init_ssl_context()
    
    def _init_ssl_context(self):
        """初始化 SSL 上下文"""
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
    
    def _make_request(self, url: str, headers: Optional[Dict] = None, data: Optional[bytes] = None) -> str:
        """发送 HTTP 请求"""
        default_headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
        
        if headers:
            default_headers.update(headers)
        
        req = urllib.request.Request(url, headers=default_headers, data=data)
        
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ssl_context) as response:
                return response.read().decode('utf-8', errors='replace')
        except Exception as e:
            raise Exception(f"请求失败: {e}")
    
    def search_baidu(self, query: str, num_results: int = 5) -> List[SearchResult]:
        """
        百度搜索
        
        Args:
            query: 搜索关键词
            num_results: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        print(f"{Fore.CYAN}[搜索] 百度搜索: {query}{Style.RESET_ALL}")
        
        try:
            # 使用百度搜索
            search_url = f"https://www.baidu.com/s?wd={urllib.parse.quote(query)}"
            html = self._make_request(search_url)
            
            results = []
            # 解析搜索结果
            import re
            
            # 提取搜索结果
            # 百度结果格式
            result_blocks = re.findall(
                r'<div[^>]*class="result"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?<span[^>]*class="content-right_8Zs40"[^>]*>(.*?)</span>',
                html,
                re.DOTALL | re.IGNORECASE
            )
            
            if not result_blocks:
                # 尝试其他格式
                result_blocks = re.findall(
                    r'<h3[^>]*class="t"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
                    html,
                    re.DOTALL | re.IGNORECASE
                )
            
            for i, block in enumerate(result_blocks[:num_results]):
                if isinstance(block, tuple):
                    url, title, snippet = block[0], block[1], block[2] if len(block) > 2 else ""
                else:
                    url, title = block, ""
                    snippet = ""
                
                # 清理 HTML 标签
                title = re.sub(r'<[^>]+>', '', title)
                snippet = re.sub(r'<[^>]+>', '', snippet)
                
                results.append(SearchResult(
                    title=title.strip() or f"结果 {i+1}",
                    url=url.strip(),
                    snippet=snippet.strip()[:200],
                    source="百度"
                ))
            
            print(f"{Fore.GREEN}[搜索] 找到 {len(results)} 个结果{Style.RESET_ALL}")
            return results
            
        except Exception as e:
            print(f"{Fore.RED}[搜索] 百度搜索失败: {e}{Style.RESET_ALL}")
            return []
    
    def search_bing(self, query: str, num_results: int = 5) -> List[SearchResult]:
        """
        Bing 搜索
        
        Args:
            query: 搜索关键词
            num_results: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        print(f"{Fore.CYAN}[搜索] Bing 搜索: {query}{Style.RESET_ALL}")
        
        try:
            search_url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={num_results}"
            html = self._make_request(search_url)
            
            results = []
            import re
            
            # Bing 结果格式 - 尝试多种模式
            # 模式 1: 标准结果格式
            result_blocks = re.findall(
                r'<li[^>]*class="b_algo"[^>]*>.*?<h2[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?</h2>.*?<p[^>]*>(.*?)</p>',
                html,
                re.DOTALL | re.IGNORECASE
            )
            
            # 模式 2: 简化格式
            if not result_blocks:
                result_blocks = re.findall(
                    r'<h2[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?</h2>',
                    html,
                    re.DOTALL | re.IGNORECASE
                )
                # 添加空 snippet
                result_blocks = [(url, title, "") for url, title in result_blocks]
            
            # 模式 3: 更宽松的匹配
            if not result_blocks:
                result_blocks = re.findall(
                    r'<a[^>]*href="(https?://[^"]+)"[^>]*>([^<]+)</a>',
                    html,
                    re.DOTALL | re.IGNORECASE
                )
                result_blocks = [(url, title, "") for url, title in result_blocks if len(title) > 10]
            
            for block in result_blocks[:num_results]:
                if isinstance(block, tuple) and len(block) >= 2:
                    url, title = block[0], block[1]
                    snippet = block[2] if len(block) > 2 else ""
                else:
                    continue
                
                # 清理 HTML 标签
                title = re.sub(r'<[^>]+>', '', title)
                snippet = re.sub(r'<[^>]+>', '', snippet) if snippet else ""
                
                # 过滤无效结果
                if not title.strip() or title.strip().lower() in ['bing', 'microsoft']:
                    continue
                
                results.append(SearchResult(
                    title=title.strip(),
                    url=url.strip(),
                    snippet=snippet.strip()[:200],
                    source="Bing"
                ))
            
            print(f"{Fore.GREEN}[搜索] 找到 {len(results)} 个结果{Style.RESET_ALL}")
            return results
            
        except Exception as e:
            print(f"{Fore.RED}[搜索] Bing 搜索失败: {e}{Style.RESET_ALL}")
            return []
    
    def get_bilibili_hot(self) -> List[TrendingItem]:
        """
        获取 B 站热搜榜
        
        Returns:
            热搜列表
        """
        print(f"{Fore.CYAN}[热搜] 获取 B 站热搜...{Style.RESET_ALL}")
        
        try:
            # B 站热搜 API
            url = "https://api.bilibili.com/x/web-interface/search/square"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://search.bilibili.com/',
            }
            
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ssl_context) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            trending = []
            if data.get('data', {}).get('trending', {}).get('list'):
                for i, item in enumerate(data['data']['trending']['list'][:20], 1):
                    trending.append(TrendingItem(
                        rank=i,
                        title=item.get('keyword', ''),
                        url=f"https://search.bilibili.com/all?keyword={urllib.parse.quote(item.get('keyword', ''))}",
                        heat=item.get('show_name', ''),
                        category=item.get('type', '')
                    ))
            
            print(f"{Fore.GREEN}[热搜] 获取到 {len(trending)} 条热搜{Style.RESET_ALL}")
            return trending
            
        except Exception as e:
            print(f"{Fore.RED}[热搜] 获取 B 站热搜失败: {e}{Style.RESET_ALL}")
            return []
    
    def get_weibo_hot(self) -> List[TrendingItem]:
        """
        获取微博热搜榜
        
        Returns:
            热搜列表
        """
        print(f"{Fore.CYAN}[热搜] 获取微博热搜...{Style.RESET_ALL}")
        
        try:
            # 微博热搜 API
            url = "https://weibo.com/ajax/side/hotSearch"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://weibo.com/',
            }
            
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ssl_context) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            trending = []
            if data.get('data', {}).get('realtime'):
                for i, item in enumerate(data['data']['realtime'][:20], 1):
                    trending.append(TrendingItem(
                        rank=i,
                        title=item.get('note', ''),
                        url=f"https://s.weibo.com/weibo?q={urllib.parse.quote(item.get('note', ''))}",
                        heat=f"{item.get('num', 0) // 10000}万",
                        category=item.get('category', '')
                    ))
            
            print(f"{Fore.GREEN}[热搜] 获取到 {len(trending)} 条热搜{Style.RESET_ALL}")
            return trending
            
        except Exception as e:
            print(f"{Fore.RED}[热搜] 获取微博热搜失败: {e}{Style.RESET_ALL}")
            return []
    
    def get_zhihu_hot(self) -> List[TrendingItem]:
        """
        获取知乎热榜
        
        Returns:
            热榜列表
        """
        print(f"{Fore.CYAN}[热搜] 获取知乎热榜...{Style.RESET_ALL}")
        
        try:
            # 知乎热榜 API
            url = "https://www.zhihu.com/api/v3/feed/topstory/hot-lists/total?limit=20"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Referer': 'https://www.zhihu.com/',
            }
            
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ssl_context) as response:
                data = json.loads(response.read().decode('utf-8'))
            
            trending = []
            if data.get('data'):
                for i, item in enumerate(data['data'], 1):
                    target = item.get('target', {})
                    trending.append(TrendingItem(
                        rank=i,
                        title=target.get('title', ''),
                        url=target.get('url', ''),
                        heat=f"{item.get('detail_text', '')}",
                        category=''
                    ))
            
            print(f"{Fore.GREEN}[热搜] 获取到 {len(trending)} 条热榜{Style.RESET_ALL}")
            return trending
            
        except Exception as e:
            print(f"{Fore.RED}[热搜] 获取知乎热榜失败: {e}{Style.RESET_ALL}")
            return []
    
    def search(self, query: str, engine: str = "bing", num_results: int = 5) -> List[SearchResult]:
        """
        通用搜索接口
        
        Args:
            query: 搜索关键词
            engine: 搜索引擎（baidu/bing）
            num_results: 返回结果数量
            
        Returns:
            搜索结果列表
        """
        if engine == "baidu":
            return self.search_baidu(query, num_results)
        elif engine == "bing":
            return self.search_bing(query, num_results)
        else:
            # 默认使用 Bing
            return self.search_bing(query, num_results)
    
    def get_hot_search(self, platform: str = "bilibili") -> List[TrendingItem]:
        """
        获取热搜榜
        
        Args:
            platform: 平台（bilibili/weibo/zhihu）
            
        Returns:
            热搜列表
        """
        if platform == "bilibili":
            return self.get_bilibili_hot()
        elif platform == "weibo":
            return self.get_weibo_hot()
        elif platform == "zhihu":
            return self.get_zhihu_hot()
        else:
            return []


# 便捷函数
_searcher = None

def get_searcher() -> WebSearchEnhanced:
    """获取搜索器实例（单例）"""
    global _searcher
    if _searcher is None:
        _searcher = WebSearchEnhanced()
    return _searcher


def search_web(query: str, engine: str = "bing", num_results: int = 5) -> List[Dict[str, str]]:
    """
    搜索网页
    
    Args:
        query: 搜索关键词
        engine: 搜索引擎
        num_results: 结果数量
        
    Returns:
        搜索结果字典列表
    """
    searcher = get_searcher()
    results = searcher.search(query, engine, num_results)
    
    return [
        {
            "title": r.title,
            "url": r.url,
            "snippet": r.snippet,
            "source": r.source
        }
        for r in results
    ]


def get_trending(platform: str = "bilibili") -> List[Dict[str, Any]]:
    """
    获取热搜榜
    
    Args:
        platform: 平台名称
        
    Returns:
        热搜条目列表
    """
    searcher = get_searcher()
    trending = searcher.get_hot_search(platform)
    
    return [
        {
            "rank": t.rank,
            "title": t.title,
            "url": t.url,
            "heat": t.heat,
            "category": t.category
        }
        for t in trending
    ]


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
        lines.append(f"   来源: {result.get('source', '未知')}")
        lines.append(f"   URL: {result.get('url', '')}")
        if result.get('snippet'):
            snippet = result.get('snippet', '')[:150]
            if len(result.get('snippet', '')) > 150:
                snippet += "..."
            lines.append(f"   摘要: {snippet}")
    
    lines.append(f"\n{Fore.CYAN}╚════════════════════════════════════════╝{Style.RESET_ALL}")
    
    return "\n".join(lines)


def format_trending(trending: List[Dict[str, Any]], platform: str = "B站") -> str:
    """
    格式化热搜榜
    
    Args:
        trending: 热搜列表
        platform: 平台名称
        
    Returns:
        格式化字符串
    """
    if not trending:
        return f"{Fore.YELLOW}未获取到热搜数据{Style.RESET_ALL}"
    
    lines = [
        f"{Fore.CYAN}╔════════════════════════════════════════╗{Style.RESET_ALL}",
        f"{Fore.CYAN}║{Style.RESET_ALL} {Fore.YELLOW}[{platform}热搜榜]{Style.RESET_ALL}".ljust(43) + f"{Fore.CYAN}║{Style.RESET_ALL}",
        f"{Fore.CYAN}╠════════════════════════════════════════╣{Style.RESET_ALL}",
    ]
    
    for item in trending[:10]:  # 只显示前10
        rank = item.get('rank', 0)
        title = item.get('title', '')
        heat = item.get('heat', '')
        
        # 根据排名设置颜色
        if rank == 1:
            rank_str = f"{Fore.RED}[{rank}]{Style.RESET_ALL}"
        elif rank == 2:
            rank_str = f"{Fore.YELLOW}[{rank}]{Style.RESET_ALL}"
        elif rank == 3:
            rank_str = f"{Fore.GREEN}[{rank}]{Style.RESET_ALL}"
        else:
            rank_str = f"[{rank}]"
        
        heat_str = f" ({heat})" if heat else ""
        lines.append(f"{rank_str} {title}{heat_str}")
    
    lines.append(f"{Fore.CYAN}╚════════════════════════════════════════╝{Style.RESET_ALL}")
    
    return "\n".join(lines)


# 工具注册
WEB_SEARCH_ENHANCED_TOOLS = {
    "search_web": search_web,
    "get_trending": get_trending,
    "format_search_results": format_search_results,
    "format_trending": format_trending,
}
