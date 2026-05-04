import os
import shutil

def clean_pycache(root_dir="."):
    """递归删除所有 __pycache__ 目录"""
    count = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "__pycache__" in dirnames:
            full_path = os.path.join(dirpath, "__pycache__")
            try:
                shutil.rmtree(full_path)
                print(f"✅ 已删除: {full_path}")
                count += 1
            except Exception as e:
                print(f"❌ 删除失败: {full_path} - {e}")
    print(f"\n🎉 共删除 {count} 个 __pycache__ 目录")

if __name__ == "__main__":
    # 默认从当前目录开始，也可以指定路径
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    clean_pycache(root)