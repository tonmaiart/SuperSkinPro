"""
SuperSkinPro — Multi-OS Rust Cross-Compilation Suite.
Run this script to automatically compile, move, and rename binaries per platform.
"""

import os
import shutil
import subprocess
import sys
import platform

def build_and_deploy():
    current_os = platform.system().lower() # 'windows', 'linux', 'darwin'
    print(f"🦀 Current Developer OS detected: {current_os.upper()}")
    
    # 1. ย้ายเข้าไปคอมไพล์โค้ดในโฟลเดอร์ Rust
    rust_dir = os.path.join(os.path.dirname(__file__), "rust_logic")
    print("🔨 Compiling Rust project in release mode...")
    
    result = subprocess.run(["cargo", "build", "--release"], cwd=rust_dir)
    if result.returncode != 0:
        print("❌ Compilation failed!")
        sys.exit(1)
        
    # 2. ตั้งค่าเป้าหมายโฟลเดอร์ปลายทาง
    target_bin_dir = os.path.join(os.path.dirname(__file__), "bin", current_os)
    os.makedirs(target_bin_dir, exist_ok=True)
    
    # 3. ตรวจสอบเงื่อนไขชื่อไฟล์เพื่อย้ายและเปลี่ยนนามสกุลตามข้อกำหนดของ Python
    source_release_dir = os.path.join(rust_dir, "target", "release")
    
    if current_os == "windows":
        src_file = os.path.join(source_release_dir, "rust_logic.dll")
        dst_file = os.path.join(target_bin_dir, "rust_logic.pyd")
    elif current_os == "linux":
        src_file = os.path.join(source_release_dir, "librust_logic.so")
        dst_file = os.path.join(target_bin_dir, "rust_logic.so")
    elif current_os == "darwin": # สำหรับ macOS
        src_file = os.path.join(source_release_dir, "librust_logic.dylib")
        dst_file = os.path.join(target_bin_dir, "rust_logic.so")
    else:
        print(f"❌ Unsupported OS: {current_os}")
        sys.exit(1)

    # 4. ทำการคัดลอกถอยหลังข้ามแดนไปยังโฟลเดอร์จัดเก็บ
    if os.path.exists(src_file):
        shutil.copy(src_file, dst_file)
        print(f"📦 Successfully deployed Binary to: bin/{current_os}/")
    else:
        print(f"❌ Built binary not found at: {src_file}")

if __name__ == "__main__":
    build_and_deploy()