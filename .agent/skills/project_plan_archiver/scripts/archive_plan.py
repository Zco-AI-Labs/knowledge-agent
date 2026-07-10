#!/usr/bin/env python3
import os
import sys
import shutil
import re

def main():
    # Define paths relative to the current workspace root directory
    workspace_root = os.getcwd()
    
    # 1. Identify source folder
    src_paths = [
        os.path.join(workspace_root, "project_plan"),
        os.path.join(workspace_root, "app", "project_plan")
    ]
    
    selected_src = None
    for path in src_paths:
        if os.path.exists(path) and os.path.isdir(path):
            selected_src = path
            break
            
    if not selected_src:
        print("Error: No 'project_plan' or 'app/project_plan' directory found in the workspace root.", file=sys.stderr)
        sys.exit(1)
        
    # 2. Identify and prepare target archive directory
    archive_dir = os.path.join(workspace_root, "docs", "archive")
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir, exist_ok=True)
        
    # 3. Determine the next version number
    version_pattern = re.compile(r"^version-(\d+) project plan$")
    max_ver = 0
    
    for entry in os.listdir(archive_dir):
        entry_path = os.path.join(archive_dir, entry)
        if os.path.isdir(entry_path):
            match = version_pattern.match(entry)
            if match:
                ver_num = int(match.group(1))
                if ver_num > max_ver:
                    max_ver = ver_num
                    
    next_ver = max_ver + 1
    new_folder_name = f"version-{next_ver} project plan"
    dest_path = os.path.join(archive_dir, new_folder_name)
    
    # 4. Perform the move
    print(f"Archiving: '{os.path.relpath(selected_src, workspace_root)}' -> '{os.path.relpath(dest_path, workspace_root)}'")
    try:
        shutil.move(selected_src, dest_path)
        print(f"Success: Archived project plan to version-{next_ver} successfully.")
    except Exception as e:
        print(f"Error: Failed to archive directory. Details: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
