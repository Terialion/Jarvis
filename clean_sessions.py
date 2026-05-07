import os
import shutil

base_dir = os.path.join(os.path.dirname(__file__), "data", "agent_threads")
if not os.path.exists(base_dir):
    print(f"目录不存在: {base_dir}")
    exit(1)

deleted = []
for item in os.listdir(base_dir):
    item_path = os.path.join(base_dir, item)
    if os.path.isdir(item_path) and (item.startswith("session_") or item.startswith("agent_session_") or item.startswith("benchmark_")):
        shutil.rmtree(item_path)
        deleted.append(item)
        print(f"已删除: {item}")

if not deleted:
    print("没有找到匹配的文件夹。")
else:
    print(f"\n共删除 {len(deleted)} 个文件夹。")