"""
B站浏览器工具 - 使用 Playwright 获取 B站视频信息
可以绕过 API 限制，直接获取 UP 主视频列表
"""

import asyncio
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
from colorama import Fore, Style


@dataclass
class BilibiliVideo:
    """B站视频数据类"""
    bvid: str
    title: str
    url: str
    cover: str
    created: str
    duration: str
    view_count: str
    like_count: str


class BilibiliBrowser:
    """B站浏览器工具类"""
    
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
    
    async def init(self):
        """初始化浏览器"""
        try:
            from playwright.async_api import async_playwright
            
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=True)
            self.context = await self.browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            self.page = await self.context.new_page()
            
            # 设置额外的 HTTP 头
            await self.page.set_extra_http_headers({
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://space.bilibili.com/',
            })
            
            return True
        except ImportError:
            print(f"{Fore.YELLOW}[B站] Playwright 未安装，请运行: pip install playwright && playwright install chromium{Style.RESET_ALL}")
            return False
        except Exception as e:
            print(f"{Fore.RED}[B站] 浏览器初始化失败: {e}{Style.RESET_ALL}")
            return False
    
    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
        if hasattr(self, 'playwright'):
            await self.playwright.stop()
    
    async def get_up_videos(self, mid: int, num_videos: int = 5) -> List[Dict[str, Any]]:
        """
        获取 UP 主的视频列表
        
        Args:
            mid: UP 主 ID
            num_videos: 获取视频数量
            
        Returns:
            视频列表
        """
        if not await self.init():
            return []
        
        try:
            url = f"https://space.bilibili.com/{mid}/video"
            print(f"{Fore.CYAN}[B站] 正在访问: {url}{Style.RESET_ALL}")
            
            # 访问页面
            await self.page.goto(url, wait_until='networkidle')
            await asyncio.sleep(2)  # 额外等待页面渲染
            
            # 等待视频列表加载 - 使用更通用的选择器
            try:
                await self.page.wait_for_selector('.video-list-item, .small-item, .video-card, [class*="video"]', timeout=15000)
            except:
                print(f"{Fore.YELLOW}[B站] 等待视频列表超时，尝试继续...{Style.RESET_ALL}")
            
            # 滚动页面加载更多视频
            for _ in range(5):
                await self.page.evaluate('window.scrollBy(0, 800)')
                await asyncio.sleep(0.8)
            
            # 提取视频信息 - 使用更通用的选择器
            videos = await self.page.evaluate(f'''
                () => {{
                    const videos = [];
                    // 尝试多种可能的选择器
                    let items = document.querySelectorAll('.video-list-item, .small-item, .video-card, .bili-video-card, [data-v-]');
                    
                    // 如果没找到，尝试更通用的
                    if (items.length === 0) {{
                        items = document.querySelectorAll('a[href*="/video/BV"]');
                    }}
                    
                    items.forEach((item, index) => {{
                        if (index >= {num_videos}) return;
                        
                        // 尝试多种选择器获取标题
                        let titleEl = item.querySelector('.title, [class*="title"], h3, .bili-video-card__info--tit');
                        let linkEl = item.tagName === 'A' ? item : item.querySelector('a[href*="/video/"]');
                        let coverEl = item.querySelector('img');
                        let playEl = item.querySelector('.play, [class*="play"], .view, [class*="view"], .bili-video-card__stats--item');
                        let dateEl = item.querySelector('.time, [class*="time"], .date, [class*="date"]');
                        let durationEl = item.querySelector('.duration, [class*="duration"], .length, [class*="length"], .bili-video-card__cover__duration');
                        
                        if (linkEl) {{
                            const href = linkEl.getAttribute('href') || '';
                            const bvidMatch = href.match(/(BV[\\w]+)/);
                            const bvid = bvidMatch ? bvidMatch[1] : '';
                            const title = titleEl?.textContent?.trim() || titleEl?.getAttribute('title') || linkEl.textContent?.trim() || '无标题';
                            
                            if (bvid && title !== '无标题') {{
                                videos.push({{
                                    bvid: bvid,
                                    title: title,
                                    url: href.startsWith('http') ? href : 'https:' + href,
                                    cover: coverEl?.getAttribute('src') || '',
                                    created: dateEl?.textContent?.trim() || '',
                                    duration: durationEl?.textContent?.trim() || '',
                                    view_count: playEl?.textContent?.trim() || ''
                                }});
                            }}
                        }}
                    }});
                    
                    return videos;
                }}
            ''')
            
            print(f"{Fore.GREEN}[B站] 成功获取 {len(videos)} 个视频{Style.RESET_ALL}")
            return videos
            
        except Exception as e:
            print(f"{Fore.RED}[B站] 获取视频失败: {e}{Style.RESET_ALL}")
            return []
        finally:
            await self.close()
    
    async def search_up(self, keyword: str) -> List[Dict[str, Any]]:
        """
        搜索 UP 主
        
        Args:
            keyword: 搜索关键词
            
        Returns:
            UP 主列表
        """
        if not await self.init():
            return []
        
        try:
            from urllib.parse import quote
            url = f"https://search.bilibili.com/all?keyword={quote(keyword)}"
            print(f"{Fore.CYAN}[B站] 正在搜索: {keyword}{Style.RESET_ALL}")
            
            await self.page.goto(url, wait_until='networkidle')
            await asyncio.sleep(1)
            
            # 点击"用户"标签
            user_tab = await self.page.query_selector('text=用户')
            if user_tab:
                await user_tab.click()
                await asyncio.sleep(1)
            
            # 提取 UP 主信息
            ups = await self.page.evaluate('''
                () => {
                    const ups = [];
                    const items = document.querySelectorAll('.up-item, [class*="up-item"], .user-item');
                    
                    items.forEach((item, index) => {
                        if (index >= 5) return;
                        
                        const nameEl = item.querySelector('.up-name, [class*="up-name"], .user-name, h3 a');
                        const linkEl = item.querySelector('a[href*="/space/"]');
                        const signEl = item.querySelector('.up-sign, [class*="sign"], .desc');
                        const fanEl = item.querySelector('.up-fans, [class*="fans"], [class*="follower"]');
                        
                        if (nameEl && linkEl) {
                            const href = linkEl.getAttribute('href') || '';
                            const midMatch = href.match(/space\/(\d+)/);
                            const mid = midMatch ? parseInt(midMatch[1]) : 0;
                            
                            ups.push({
                                mid: mid,
                                name: nameEl.textContent?.trim() || '',
                                url: href.startsWith('http') ? href : 'https:' + href,
                                sign: signEl?.textContent?.trim() || '',
                                follower: fanEl?.textContent?.trim() || ''
                            });
                        }
                    });
                    
                    return ups;
                }
            ''')
            
            print(f"{Fore.GREEN}[B站] 找到 {len(ups)} 个 UP 主{Style.RESET_ALL}")
            return ups
            
        except Exception as e:
            print(f"{Fore.RED}[B站] 搜索 UP 主失败: {e}{Style.RESET_ALL}")
            return []
        finally:
            await self.close()


# 便捷函数
async def find_up_and_get_videos(up_name: str, num_videos: int = 5) -> Dict[str, Any]:
    """
    查找 UP 主并获取其最新视频
    
    Args:
        up_name: UP 主名称
        num_videos: 获取视频数量
        
    Returns:
        包含 UP 主信息和视频列表的字典
    """
    print(f"{Fore.CYAN}[B站] 正在查找 UP 主 '{up_name}' 的最新视频...{Style.RESET_ALL}")
    
    browser = BilibiliBrowser()
    
    # 1. 搜索 UP 主
    ups = await browser.search_up(up_name)
    
    if not ups:
        return {
            'success': False,
            'error': f'未找到名为 "{up_name}" 的 UP 主',
            'up_info': None,
            'videos': []
        }
    
    # 2. 获取第一个匹配的 UP 主视频
    up = ups[0]
    videos = await browser.get_up_videos(up['mid'], num_videos)
    
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
        f"{Fore.CYAN}║{Style.RESET_ALL} {Fore.YELLOW}B站 UP 主: {up['name']}{Style.RESET_ALL}".ljust(61) + f"{Fore.CYAN}║{Style.RESET_ALL}",
        f"{Fore.CYAN}╠══════════════════════════════════════════════════════════════╣{Style.RESET_ALL}",
        f"  签名: {up.get('sign', '暂无签名')[:50]}{'...' if len(up.get('sign', '')) > 50 else ''}",
        f"  粉丝: {up.get('follower', '未知')}  |  主页: {up['url']}",
        "",
        f"{Fore.CYAN}  最新视频:{Style.RESET_ALL}",
        f"{Fore.CYAN}  {'─' * 58}{Style.RESET_ALL}",
    ]
    
    for i, video in enumerate(videos, 1):
        title = video['title'][:45] + '...' if len(video['title']) > 45 else video['title']
        lines.extend([
            f"",
            f"  {Fore.GREEN}{i}. {title}{Style.RESET_ALL}",
            f"     发布时间: {video.get('created', '未知')}  |  时长: {video.get('duration', '未知')}",
            f"     播放量: {video.get('view_count', '未知')}",
            f"     链接: {video['url']}",
        ])
    
    lines.append(f"{Fore.CYAN}╚══════════════════════════════════════════════════════════════╝{Style.RESET_ALL}")
    
    return "\n".join(lines)


# 同步包装函数
def find_up_videos_sync(up_name: str, num_videos: int = 5) -> Dict[str, Any]:
    """同步版本的查找 UP 主视频"""
    return asyncio.run(find_up_and_get_videos(up_name, num_videos))


# 工具注册
BILIBILI_BROWSER_TOOLS = {
    "find_up_videos_sync": find_up_videos_sync,
    "format_up_videos": format_up_videos,
}


# 测试代码
if __name__ == "__main__":
    result = find_up_videos_sync("MEETFOOD 觅食", num_videos=3)
    print(format_up_videos(result))
