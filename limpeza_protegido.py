import os
import sys
import tempfile
import shutil
import subprocess
from pathlib import Path

# CRITICAL: Set environment variables BEFORE importing streamlit
def setup_environment():
    """Configure environment variables for containerized deployment"""
    
    # Streamlit configuration for headless mode
    os.environ["STREAMLIT_SERVER_HEADLESS"] = "true"
    os.environ["STREAMLIT_BROWSER_GATHER_USAGE_STATS"] = "false"
    os.environ["STREAMLIT_SERVER_FILE_WATCHER_TYPE"] = "none"
    os.environ["STREAMLIT_CONFIG_SHOW_ERROR_DETAILS"] = "false"
    os.environ["STREAMLIT_SERVER_ENABLE_CORS"] = "false"
    os.environ["STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION"] = "false"
    
    # Force Streamlit to use a writable directory
    # Try different writable locations in order of preference
    writable_dirs = [
        os.path.expanduser("~"),  # User home
        "/tmp",                   # Temp directory
        os.getcwd(),             # Current working directory
        "/app"                   # Common app directory in containers
    ]
    
    streamlit_home = None
    for base_dir in writable_dirs:
        try:
            test_dir = os.path.join(base_dir, ".streamlit")
            os.makedirs(test_dir, exist_ok=True)
            # Test write permission
            test_file = os.path.join(test_dir, "test_write")
            with open(test_file, 'w') as f:
                f.write("test")
            os.remove(test_file)
            streamlit_home = base_dir
            break
        except (PermissionError, OSError):
            continue
    
    if streamlit_home:
        # Set the home directory for Streamlit
        os.environ["HOME"] = streamlit_home
        os.environ["STREAMLIT_CONFIG_DIR"] = os.path.join(streamlit_home, ".streamlit")
        
        # Create config directory and file
        config_dir = os.path.join(streamlit_home, ".streamlit")
        os.makedirs(config_dir, exist_ok=True)
        
        # Create comprehensive config.toml
        config_path = os.path.join(config_dir, "config.toml")
        config_content = """
[server]
headless = true
port = 8501
address = "0.0.0.0"
fileWatcherType = "none"
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false
serverAddress = "0.0.0.0"
serverPort = 8501

[global]
developmentMode = false
logLevel = "error"

[logger]
level = "error"
"""
        
        with open(config_path, "w") as f:
            f.write(config_content)
            
        print(f"Streamlit configured to use: {streamlit_home}")
        return True
    else:
        print("WARNING: Could not find writable directory for Streamlit config")
        return False

# Setup environment BEFORE importing streamlit
setup_environment()

# NOW import streamlit
import streamlit as st

def check_git_availability():
    """Check if git is available in the system"""
    try:
        result = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False

def load_from_private_repo():
    """Load Text Cleaner code from repository"""
    
    # Get configuration from environment variables
    github_token = os.environ.get("GITHUB_TOKEN", "")
    github_user = os.environ.get("GITHUB_USER", "")
    repo_name = os.environ.get("REPO_NAME", "")
    main_file = os.environ.get("TEXT_CLEANER_MAIN_FILE", "limpeza_protegido.py")
    
    if not all([github_user, repo_name]):
        show_setup_instructions()
        return False
    
    # Check if git is available
    if not check_git_availability():
        st.info("ℹ️ Git not available - using GitHub API method...")
        return load_with_requests()
    
    temp_dir = None
    try:
        # Create temporary directory
        temp_dir = tempfile.mkdtemp()
        
        # Repository URL - try with/without authentication
        if github_token:
            repo_url = f"https://{github_user}:{github_token}@github.com/{github_user}/{repo_name}.git"
        else:
            repo_url = f"https://github.com/{github_user}/{repo_name}.git"
        
        with st.spinner("🔄 Loading Text Cleaner application..."):
            # Clone repository
            result = subprocess.run([
                "git", "clone", repo_url, temp_dir
            ], capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                st.error(f"❌ Git clone error: {result.stderr}")
                # If fails with token, try without token (for public repos)
                if github_token:
                    st.info("🔄 Trying public access...")
                    repo_url = f"https://github.com/{github_user}/{repo_name}.git"
                    result = subprocess.run([
                        "git", "clone", repo_url, temp_dir
                    ], capture_output=True, text=True, timeout=30)
                    
                    if result.returncode != 0:
                        st.error(f"❌ Public access error: {result.stderr}")
                        st.info("🔄 Falling back to GitHub API method...")
                        return load_with_requests()
                else:
                    st.info("🔄 Falling back to GitHub API method...")
                    return load_with_requests()
        
        # Add to Python path
        sys.path.insert(0, temp_dir)
        
        # Check if main file exists
        main_path = Path(temp_dir) / main_file
        if not main_path.exists():
            st.error(f"❌ File {main_file} not found in repository")
            available_files = [f.name for f in Path(temp_dir).glob("*.py")]
            if available_files:
                st.info(f"Available files: {', '.join(available_files)}")
            return False
        
        # Execute main file
        try:
            with open(main_path, 'r', encoding='utf-8') as f:
                code_content = f.read()
            
            # Execute code
            exec(code_content, globals())
            return True
            
        except Exception as e:
            st.error(f"❌ Error executing {main_file}: {e}")
            return False
    
    except subprocess.TimeoutExpired:
        st.error("❌ Git clone timeout - falling back to GitHub API...")
        return load_with_requests()
    except Exception as e:
        st.error(f"❌ Git method failed: {e} - falling back to GitHub API...")
        return load_with_requests()
    
    finally:
        # Cleanup (will run even if exception occurs)
        if temp_dir and Path(temp_dir).exists():
            shutil.rmtree(temp_dir, ignore_errors=True)

def load_with_requests():
    """Alternative method using GitHub API (works without git)"""
    
    github_token = os.environ.get("GITHUB_TOKEN", "")
    github_user = os.environ.get("GITHUB_USER", "")
    repo_name = os.environ.get("REPO_NAME", "")
    main_file = os.environ.get("TEXT_CLEANER_MAIN_FILE", "limpeza_protegido.py")
    
    try:
        import requests
        
        # GitHub API URL for the file
        api_url = f"https://api.github.com/repos/{github_user}/{repo_name}/contents/{main_file}"
        
        headers = {
            "Accept": "application/vnd.github.v3.raw",
            "User-Agent": "Streamlit-App"
        }
        
        if github_token:
            headers["Authorization"] = f"token {github_token}"
        
        with st.spinner("🔥 Downloading Text Cleaner code via GitHub API..."):
            response = requests.get(api_url, headers=headers, timeout=15)
            
            if response.status_code == 200:
                code_content = response.text
                
                # Validate that we got Python code
                if not code_content.strip():
                    st.error("❌ Downloaded file is empty")
                    return False
                
                if not (code_content.startswith('#') or 'import' in code_content or 'def ' in code_content):
                    st.warning("⚠️ Downloaded content doesn't look like Python code")
                
                # Execute the code
                try:
                    exec(code_content, globals())
                    st.success("✅ Text Cleaner loaded successfully via GitHub API!")
                    return True
                except Exception as exec_error:
                    st.error(f"❌ Error executing downloaded code: {exec_error}")
                    st.code(code_content[:500] + "..." if len(code_content) > 500 else code_content)
                    return False
                    
            elif response.status_code == 404:
                st.error(f"❌ File '{main_file}' not found in repository")
                
                # Try to list available files
                try:
                    contents_url = f"https://api.github.com/repos/{github_user}/{repo_name}/contents"
                    contents_response = requests.get(contents_url, headers=headers, timeout=10)
                    
                    if contents_response.status_code == 200:
                        contents = contents_response.json()
                        python_files = [item['name'] for item in contents if item['name'].endswith('.py')]
                        
                        if python_files:
                            st.info(f"Available Python files: {', '.join(python_files)}")
                            st.info("💡 Update TEXT_CLEANER_MAIN_FILE environment variable with the correct filename")
                        else:
                            st.info("No Python files found in repository root")
                            
                except Exception:
                    pass  # Ignore errors when trying to list files
                    
                return False
                
            elif response.status_code == 403:
                st.error("❌ Access denied to repository")
                if not github_token:
                    st.info("💡 This might be a private repository. Add GITHUB_TOKEN to access it.")
                else:
                    st.info("💡 Check if your GITHUB_TOKEN has the correct permissions")
                return False
                
            elif response.status_code == 401:
                st.error("❌ Invalid GitHub token")
                st.info("💡 Check your GITHUB_TOKEN value")
                return False
                
            else:
                st.error(f"❌ GitHub API error: {response.status_code}")
                st.info(f"Response: {response.text[:200]}")
                return False
                
    except requests.exceptions.Timeout:
        st.error("❌ Timeout downloading from GitHub API")
        return False
    except requests.exceptions.ConnectionError:
        st.error("❌ Connection error - check internet connectivity")
        return False
    except ImportError:
        st.error("❌ 'requests' library not available")
        st.info("💡 Add 'requests' to your requirements.txt")
        return False
    except Exception as e:
        st.error(f"❌ Unexpected error in GitHub API method: {e}")
        return False

def show_setup_instructions():
    """Show Text Cleaner specific setup instructions"""
    
    st.title("🧹 Text Cleaner App with Private Repository")
    st.warning("⚠️ Configuration required!")
    
    st.markdown("""
    ## 📋 How to Configure Text Cleaner App
    
    ### 1. Use GitHub Repository
    - Recommended repository: `MarioNunes35/TextCleaner` or similar
    - Add your Text Cleaner code as `limpeza_protegido.py`
    
    ### 2. Repository Structure
    ```
    TextCleaner/
    ├── limpeza_protegido.py       # Main Text Cleaner code with auth
    ├── requirements.txt            # Dependencies
    └── README.md                  # Documentation
    ```
    
    ### 3. Configure Secrets in HF Spaces
    """)
    
    st.code("""
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxx (optional for public repos)
GITHUB_USER=MarioNunes35
REPO_NAME=TextCleaner
TEXT_CLEANER_MAIN_FILE=limpeza_protegido.py
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
    """)
    
    st.markdown("""
    ### 4. Specific Environment Variables
    - `TEXT_CLEANER_MAIN_FILE`: Text Cleaner main file name (default: `limpeza_protegido.py`)
    - `GITHUB_TOKEN`: Optional for public repositories, required for private ones
    - Other variables (`GITHUB_USER`, `REPO_NAME`) are mandatory
    
    ### 5. Required Dependencies (requirements.txt)
    ```
    streamlit
    st-supabase-connection
    requests
    ```
    """)
    
    # Basic demo
    st.markdown("---")
    st.subheader("🎬 Configuration Status")
    
    if st.button("🔄 Check Text Cleaner Configuration"):
        github_token = os.environ.get("GITHUB_TOKEN", "")
        github_user = os.environ.get("GITHUB_USER", "")
        repo_name = os.environ.get("REPO_NAME", "")
        text_cleaner_file = os.environ.get("TEXT_CLEANER_MAIN_FILE", "limpeza_protegido.py")
        
        if github_token and github_user and repo_name:
            st.success("✅ Variables configured!")
            st.info(f"📁 Repository: {github_user}/{repo_name}")
            st.info(f"📄 Text Cleaner file: {text_cleaner_file}")
        elif github_user and repo_name:
            st.info("ℹ️ Public mode detected (no GITHUB_TOKEN)")
            st.info(f"📁 Repository: {github_user}/{repo_name}")
            st.info(f"📄 Text Cleaner file: {text_cleaner_file}")
        else:
            missing = []
            if not github_user: missing.append("GITHUB_USER") 
            if not repo_name: missing.append("REPO_NAME")
            
            st.error(f"❌ Missing mandatory variables: {', '.join(missing)}")
            st.info("💡 GITHUB_TOKEN is optional for public repositories")

def main():
    """Main function"""
    
    st.set_page_config(
        page_title="Text Cleaner Private App",
        page_icon="🧹",
        layout="wide"
    )
    
    # Try to load from private repository
    if not load_from_private_repo():
        # If it fails, show instructions
        pass  # show_setup_instructions() was already called

if __name__ == "__main__":
    main()
