"""
B站工具 - 专门用于访问和搜索 Bilibili 内容
提供 UP 主视频查询、搜索、热门内容获取等功能
"""

import json
import urllib.request
import urllib.error
import urllib.parse
import ssl
import re
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from colorama import Fore, Style


@dataclass
class BilibiliVideo:
    """B站视频数据类"""
    bvid: str
    title: str
    description: str
    author: str
    mid: int  # UP主ID
    pic: str  # 封面图
    url: str
    created: datetime
    duration: str
    view_count: int
    like_count: int
    coin_count: int


@dataclass
class BilibiliUPInfo:
    """B站 UP 主信息"""
    mid: int
    name: str
    face: str  # 头像
    sign: str  # 签名
    follower: int  # 粉丝数
    following: int  # 关注数
    video_count: int  # 视频数


class BilibiliTools:
    """B站工具类"""
    
    def __init__(self):
        self.timeout = 15
        self._init_ssl_context()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://search.bilibili.com/',
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        }
    
    def _init_ssl_context(self):
        """初始化 SSL 上下文"""
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = False
        self.ssl_context.verify_mode = ssl.CERT_NONE
    
    def _make_request(self, url: str, headers: Optional[Dict] = None) -> Dict:
        """发送 HTTP 请求并返回 JSON"""
        request_headers = self.headers.copy()
        if headers:
            request_headers.update(headers)
        
        req = urllib.request.Request(url, headers=request_headers)
        
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=self.ssl_context) as response:
                data = json.loads(response.read().decode('utf-8', errors='replace'))
                return data
        except Exception as e:
            raise Exception(f"请求失败: {e}")
    
    def search_up(self, keyword: str) -> List[Dict[str, Any]]:
        """
        搜索 UP 主
        
        Args:
            keyword: UP 主名称关键词
            
        Returns:
            UP 主列表
        """
        print(f"{Fore.CYAN}[B站] 搜索 UP 主: {keyword}{Style.RESET_ALL}")
        
        try:
            # B站搜索 API - 搜索用户
            encoded_keyword = urllib.parse.quote(keyword)
            url = f"https://api.bilibili.com/x/web-interface/search/type?keyword={encoded_keyword}&search_type=bili_user"
            
            data = self._make_request(url)
            
            if data.get('code') != 0:
                print(f"{Fore.YELLOW}[B站] API 返回错误: {data.get('message', '未知错误')}{Style.RESET_ALL}")
                return []
            
            users = []
            user_list = data.get('data', {}).get('result', [])
            
            for user in user_list[:5]:  # 只取前5个
                users.append({
                    'mid': user.get('mid'),
                    'name': user.get('uname', ''),
                    'sign': user.get('usign', ''),
                    'follower': user.get('followers', 0),
                    'video_count': user.get('videos', 0),
                    'face': user.get('upic', ''),
                    'level': user.get('level', 0),
                    'url': f"https://space.bilibili.com/{user.get('mid')}"
                })
            
            print(f"{Fore.GREEN}[B站] 找到 {len(users)} 个 UP 主{Style.RESET_ALL}")
            return users
            
        except Exception as e:
            print(f"{Fore.RED}[B站] 搜索 UP 主失败: {e}{Style.RESET_ALL}")
            return []
    
    def get_up_videos(self, mid: int, page: int = 1, page_size: int = 10) -> List[Dict[str, Any]]:
        """
        获取 UP 主的视频列表
        
        Args:
            mid: UP 主 ID
            page: 页码
            page_size: 每页数量
            
        Returns:
            视频列表
        """
        print(f"{Fore.CYAN}[B站] 获取 UP 主视频 (mid={mid}){Style.RESET_ALL}")
        
        try:
            # B站用户视频 API
            url = f"https://api.bilibili.com/x/space/wbi/arc/search?mid={mid}&pn={page}&ps={page_size}&order=pubdate"
            
            data = self._make_request(url)
            
            if data.get('code') != 0:
                print(f"{Fore.YELLOW}[B站] API 返回错误: {data.get('message', '未知错误')}{Style.RESET_ALL}")
                return []
            
            videos = []
            vlist = data.get('data', {}).get('list', {}).get('vlist', [])
            
            for video in vlist:
                created_timestamp = video.get('created', 0)
                created_time = datetime.fromtimestamp(created_timestamp) if created_timestamp else None
                
                videos.append({
                    'bvid': video.get('bvid', ''),
                    'title': video.get('title', ''),
                    'description': video.get('description', ''),
                    'pic': video.get('pic', ''),
                    'url': f"https://www.bilibili.com/video/{video.get('bvid', '')}",
                    'created': created_time.strftime('%Y-%m-%d %H:%M') if created_time else '',
                    'duration': video.get('length', ''),
                    'view_count': video.get('play', 0),
                    'comment_count': video.get('comment', 0),
                })
            
            print(f"{Fore.GREEN}[B站] 获取到 {len(videos)} 个视频{Style.RESET_ALL}")
            return videos
            
        except Exception as e:
            print(f"{Fore.RED}[B站] 获取视频失败: {e}{Style.RESET_ALL}")
            return []
    
    def search_videos(self, keyword: str, num_results: int = 10) -> List[Dict[str, Any]]:
        """
        搜索视频
        
        Args:
            keyword: 搜索关键词
            num_results: 返回结果数量
            
        Returns:
            视频列表
        """
        print(f"{Fore.CYAN}[B站] 搜索视频: {keyword}{Style.RESET_ALL}")
        
        try:
            encoded_keyword = urllib.parse.quote(keyword)
            url = f"https://api.bilibili.com/x/web-interface/search/all?keyword={encoded_keyword}"
            
            data = self._make_request(url)
            
            if data.get('code') != 0:
                return []
            
            videos = []
            results = data.get('data', {}).get('result', [])
            
            # 找到视频类型的结果
            for result in results:
                if result.get('result_type') == 'video':
                    video_list = result.get('data', [])
                    for video in video_list[:num_results]:
                        videos.append({
                            'bvid': video.get('bvid', ''),
                            'title': video.get('title', '').replace('<em class="keyword">', '').replace('</em>', ''),
                            'description': video.get('description', ''),
                            'author': video.get('author', ''),
                            'pic': video.get('pic', ''),
                            'url': f"https://www.bilibili.com/video/{video.get('bvid', '')}",
                            'duration': video.get('duration', ''),
                            'view_count': video.get('play', 0),
                            'pubdate': video.get('pubdate', ''),
                        })
                    break
            
            print(f"{Fore.GREEN}[B站] 找到 {len(videos)} 个视频{Style.RESET_ALL}")
            return videos
            
        except Exception as e:
            print(f"{Fore.RED}[B站] 搜索视频失败: {e}{Style.RESET_ALL}")
            return []


# 便捷函数
_bili_tools = None

def get_bili_tools() -> BilibiliTools:
    """获取 B站工具实例（单例）"""
    global _bili_tools
    if _bili_tools is None:
        _bili_tools = BilibiliTools()
    return _bili_tools


def search_bilibili_up(keyword: str) -> List[Dict[str, Any]]:
    """搜索 B站 UP 主"""
    return get_bili_tools().search_up(keyword)


def get_up_latest_videos(mid: int, num: int = 5) -> List[Dict[str, Any]]:
    """获取 UP 主最新视频"""
    return get_bili_tools().get_up_videos(mid, page=1, page_size=num)


def search_bilibili_videos(keyword: str, num_results: int = 10) -> List[Dict[str, Any]]:
    """搜索 B站视频"""
    return get_bili_tools().search_videos(keyword, num_results)


def find_up_and_get_videos(up_name: str, num_videos: int = 5) -> Dict[str, Any]:
    """
    查找 UP 主并获取其最新视频（一站式功能）
    
    Args:
        up_name: UP 主名称
        num_videos: 获取视频数量
        
    Returns:
        包含 UP 主信息和视频列表的字典
    """
    print(f"{Fore.CYAN}[B站] 正在查找 UP 主 '{up_name}' 的最新视频...{Style.RESET_ALL}")
    
    # 1. 搜索 UP 主
    ups = search_bilibili_up(up_name)
    
    if not ups:
        return {
            'success': False,
            'error': f'未找到名为 "{up_name}" 的 UP 主',
            'up_info': None,
            'videos': []
        }
    
    # 2. 获取第一个匹配的 UP 主视频
    up = ups[0]
    videos = get_up_latest_videos(up['mid'], num_videos)
    
    return {
        'success': True,
        'up_info': up,
        'videos': videos
    }


def format_up_videos(result: Dict[str, Any]) -> str:
    """
    格式化 UP 主视频信息为字符串
    
    Args:
        result: find_up_and_get_videos 的返回结果
        
    Returns:
        格式化字符串
    """
    if not result['success']:
        return f"{Fore.YELLOW}❌ {result['error']}{Style.RESET_ALL}"
    
    up = result['up_info']
    videos = result['videos']
    
    lines = [
        f"{Fore.CYAN}╔══════════════════════════════════════════════════════════════╗{Style.RESET_ALL}",
        f"{Fore.CYAN}║{Style.RESET_ALL} {Fore.YELLOW}📺 B站 UP 主: {up['name']}{Style.RESET_ALL}".ljust(61) + f"{Fore.CYAN}║{Style.RESET_ALL}",
        f"{Fore.CYAN}╠══════════════════════════════════════════════════════════════╣{Style.RESET_ALL}",
        f"  签名: {up['sign'][:50]}{'...' if len(up['sign']) > 50 else ''}",
        f"  粉丝: {up['follower']:,}  |  视频数: {up['video_count']}",
        f"  主页: {up['url']}",
        "",
        f"{Fore.CYAN}  📹 最新视频:{Style.RESET_ALL}",
        f"{Fore.CYAN}  {'─' * 58}{Style.RESET_ALL}",
    ]
    
    for i, video in enumerate(videos, 1):
        title = video['title'][:40] + '...' if len(video['title']) > 40 else video['title']
        lines.extend([
            f"",
            f"  {Fore.GREEN}{i}. {title}{Style.RESET_ALL}",
            f"     发布时间: {video['created']}  |  时长: {video['duration']}",
            f"     播放量: {video['view_count']:,}  |  评论: {video['comment_count']:,}",
            f"     链接: {video['url']}",
        ])
    
    lines.append(f"{Fore.CYAN}╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
    
    return "\n".join(lines)


# 工具注册
BILIBILI_TOOLS = {
    "search_bilibili_up": search_bilibili_up,
    "get_up_latest_videos": get_up_latest_videos,
    "search_bilibili_videos": search_bilibili_videos,
    "find_up_and_get_videos": find_up_and_get_videos,
    "format_up_videos": format_up_videos,
}


# 测试代码
if __name__ == "__main__":
    # 测试查找 MEETFOOD 觅食
    result = find_up_and_get_videos("MEETFOOD 觅食", num_videos=3)
    print(format_up_videos(result))
