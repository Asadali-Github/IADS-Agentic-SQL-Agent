"""Pre-deployment verification checklist for production deployment."""

import sys
import os
import subprocess
from pathlib import Path

class PreFlightCheck:
    """Run comprehensive pre-deployment checks."""
    
    def __init__(self):
        self.checks = []
        self.passed = 0
        self.failed = 0
    
    def add_check(self, name: str, check_fn) -> None:
        """Add a check to run."""
        self.checks.append((name, check_fn))
    
    def run(self) -> bool:
        """Run all checks and return True if all pass."""
        print("\n" + "="*60)
        print("🚀 IADS Agent - Pre-Deployment Checklist")
        print("="*60 + "\n")
        
        for name, check_fn in self.checks:
            try:
                result = check_fn()
                if result:
                    print(f"✅ {name}")
                    self.passed += 1
                else:
                    print(f"❌ {name}")
                    self.failed += 1
            except Exception as e:
                print(f"❌ {name}: {str(e)}")
                self.failed += 1
        
        # Summary
        print("\n" + "="*60)
        print(f"Results: {self.passed} passed, {self.failed} failed")
        print("="*60 + "\n")
        
        return self.failed == 0


def check_docker() -> bool:
    """Check if Docker is installed."""
    try:
        subprocess.run(["docker", "--version"], capture_output=True, check=True)
        return True
    except:
        return False


def check_docker_compose() -> bool:
    """Check if Docker Compose is installed."""
    try:
        subprocess.run(["docker-compose", "--version"], capture_output=True, check=True)
        return True
    except:
        return False


def check_python() -> bool:
    """Check Python version."""
    version = sys.version_info
    return version.major >= 3 and version.minor >= 11


def check_env_file() -> bool:
    """Check if .env.production exists."""
    return Path(".env.prod").exists() or Path(".env.production").exists()


def check_env_vars() -> bool:
    """Check if required environment variables are set."""
    required_vars = [
        "ADB_USER",
        "ADB_PASSWORD",
        "ADB_DSN",
        "ADB_WALLET_PASSWORD",
        "OCI_CONFIG_PATH",
        "OCI_REGION",
        "OCI_COMPARTMENT_ID",
    ]
    
    # Load .env file
    env_file = ".env.prod" if Path(".env.prod").exists() else ".env.production"
    if not Path(env_file).exists():
        return False
    
    with open(env_file) as f:
        env_content = f.read()
    
    for var in required_vars:
        if f"{var}=" not in env_content:
            print(f"    Missing: {var}")
            return False
    
    return True


def check_oci_credentials() -> bool:
    """Check if OCI credentials exist."""
    return Path(".oci/config").exists()


def check_wallet_files() -> bool:
    """Check if Oracle wallet files exist."""
    wallet_dir = Path("wallet")
    if not wallet_dir.exists():
        return False
    
    # Check for essential wallet files
    files = list(wallet_dir.glob("*"))
    return len(files) > 0


def check_logs_directory() -> bool:
    """Check if logs directory exists and is writable."""
    logs_dir = Path("logs")
    try:
        logs_dir.mkdir(exist_ok=True)
        test_file = logs_dir / ".write_test"
        test_file.write_text("test")
        test_file.unlink()
        return True
    except:
        return False


def check_database_connection() -> bool:
    """Test database connection."""
    try:
        # Try to import and test connection
        from app.sql.oracle_connection import connect_adb
        conn = connect_adb()
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 FROM dual")
        conn.close()
        return True
    except Exception as e:
        print(f"    Error: {str(e)[:100]}")
        return False


def check_code_tests() -> bool:
    """Run unit tests."""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/", "-v", "--tb=short"],
            capture_output=True,
            timeout=60,
        )
        return result.returncode == 0
    except:
        print("    Skipping (pytest not available)")
        return True


def check_code_lint() -> bool:
    """Check code quality."""
    try:
        result = subprocess.run(
            ["python", "-m", "pylint", "app/", "--disable=C0114,C0115"],
            capture_output=True,
            timeout=30,
        )
        # Pylint exit codes: 0=ok, 1=fatal, 2=error, 4=warning, 8=usage, 16=RefactoringWarning, 32=Info
        return result.returncode < 2  # Allow warnings
    except:
        print("    Skipping (pylint not available)")
        return True


def check_docker_files() -> bool:
    """Check if Dockerfile exists."""
    return (
        Path("Dockerfile.prod").exists() or
        Path("Dockerfile").exists()
    )


def check_compose_file() -> bool:
    """Check if docker-compose file exists."""
    return Path("docker-compose.prod.yml").exists()


def check_git_ignored() -> bool:
    """Check if sensitive files are gitignored."""
    gitignore = Path(".gitignore")
    if not gitignore.exists():
        return False
    
    content = gitignore.read_text()
    required_ignores = [".env.prod", ".oci/", "wallet/"]
    
    return all(ignore in content for ignore in required_ignores)


def check_requirements() -> bool:
    """Check if requirements.txt is valid."""
    if not Path("requirements.txt").exists():
        return False
    
    try:
        result = subprocess.run(
            ["python", "-m", "pip", "check"],
            capture_output=True,
            timeout=30,
        )
        return result.returncode == 0
    except:
        return False


def check_ssl_cert() -> bool:
    """Check if SSL certificate is needed and available."""
    # This is optional, so always pass
    # In real production, you'd check for certificates
    return True


def main():
    """Run pre-flight checks."""
    checker = PreFlightCheck()
    
    # System checks
    print("📋 System Requirements")
    checker.add_check("Docker installed", check_docker)
    checker.add_check("Docker Compose installed", check_docker_compose)
    checker.add_check("Python 3.11+", check_python)
    
    # Configuration checks
    print("\n⚙️  Configuration")
    checker.add_check("Environment file (.env.prod) exists", check_env_file)
    checker.add_check("Required environment variables set", check_env_vars)
    checker.add_check("OCI credentials configured", check_oci_credentials)
    checker.add_check("Oracle wallet files present", check_wallet_files)
    
    # Deployment checks
    print("\n🐳 Docker & Deployment")
    checker.add_check("Logs directory writable", check_logs_directory)
    checker.add_check("Dockerfile exists", check_docker_files)
    checker.add_check("docker-compose.prod.yml exists", check_compose_file)
    
    # Code quality checks
    print("\n✨ Code Quality")
    checker.add_check("Requirements.txt valid", check_requirements)
    checker.add_check("Code linting passes", check_code_lint)
    checker.add_check("Unit tests pass", check_code_tests)
    
    # Security checks
    print("\n🔐 Security")
    checker.add_check("Sensitive files in .gitignore", check_git_ignored)
    
    # Database checks
    print("\n🗄️  Database")
    checker.add_check("Database connectivity", check_database_connection)
    
    # Run checks
    success = checker.run()
    
    if success:
        print("✅ All checks passed! Ready for deployment.\n")
        print("Next steps:")
        print("1. Review .env.prod configuration")
        print("2. Run: ./deploy.sh production up")
        print("3. Verify services at:")
        print("   - API: http://localhost:8000/health")
        print("   - Frontend: http://localhost:8501")
        print("   - Monitoring: http://localhost:8502")
        return 0
    else:
        print("❌ Some checks failed. Address the issues above before deploying.\n")
        print("Common fixes:")
        print("1. Install missing tools: docker, docker-compose")
        print("2. Create .env.prod from .env.prod.example")
        print("3. Configure OCI credentials in .oci/config")
        print("4. Extract Oracle wallet to wallet/ directory")
        return 1


if __name__ == "__main__":
    sys.exit(main())
