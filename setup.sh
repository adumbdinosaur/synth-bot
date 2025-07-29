#!/bin/bash

# Telegram UserBot Setup Script
# This script helps you set up the Telegram UserBot application

set -e

echo "🚀 Telegram UserBot Setup Script"
echo "================================="
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_step() {
    echo -e "${BLUE}[STEP]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   print_error "This script should not be run as root for security reasons"
   exit 1
fi

# Check required tools
check_requirements() {
    print_step "Checking requirements..."
    
    local missing_tools=()
    
    # Check if we're in a Nix environment
    if [ -n "$IN_NIX_SHELL" ] || [ -n "$NIX_PATH" ]; then
        print_status "Detected Nix environment ❄️"
        
        # In Nix, we expect tools to be available
        if ! command -v python3 &> /dev/null; then
            print_error "Python3 not available. Make sure you're in the nix-shell:"
            echo "  nix-shell"
            exit 1
        fi
    else
        # Regular system checks
        if ! command -v python3 &> /dev/null; then
            missing_tools+=("python3")
        fi
        
        if ! command -v pip3 &> /dev/null; then
            missing_tools+=("pip3")
        fi
    fi
    
    if ! command -v docker &> /dev/null; then
        missing_tools+=("docker")
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        missing_tools+=("docker-compose")
    fi
    
    if [ ${#missing_tools[@]} -ne 0 ]; then
        print_error "Missing required tools: ${missing_tools[*]}"
        echo "Please install the missing tools and run this script again."
        exit 1
    fi
    
    print_status "All requirements satisfied!"
}

# Generate secure secret key
generate_secret_key() {
    python3 -c "import secrets; print(secrets.token_urlsafe(32))"
}

# Setup environment file
setup_environment() {
    print_step "Setting up environment configuration..."
    
    if [ ! -f .env ]; then
        cp .env.example .env
        print_status "Created .env file from template"
    else
        print_warning ".env file already exists, skipping creation"
        return
    fi
    
    echo
    echo "📝 Please provide the following information:"
    echo
    
    # Get Telegram API credentials
    while true; do
        read -p "Enter your Telegram API ID (from https://my.telegram.org): " api_id
        if [[ $api_id =~ ^[0-9]+$ ]]; then
            break
        else
            print_error "API ID must be a number"
        fi
    done
    
    read -p "Enter your Telegram API Hash (from https://my.telegram.org): " api_hash
    
    # Generate secret key
    secret_key=$(generate_secret_key)
    
    # Update .env file
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s/your_api_id/$api_id/g" .env
        sed -i '' "s/your_api_hash/$api_hash/g" .env
        sed -i '' "s/your-super-secret-key-here-change-this-in-production/$secret_key/g" .env
    else
        # Linux
        sed -i "s/your_api_id/$api_id/g" .env
        sed -i "s/your_api_hash/$api_hash/g" .env
        sed -i "s/your-super-secret-key-here-change-this-in-production/$secret_key/g" .env
    fi
    
    print_status "Environment file configured successfully!"
}

# Create necessary directories
create_directories() {
    print_step "Creating necessary directories..."
    
    mkdir -p sessions
    mkdir -p data
    
    print_status "Directories created!"
}

# Setup Python virtual environment
setup_python_env() {
    print_step "Setting up Python virtual environment..."
    
    # Check if we're in Nix shell and venv is already managed
    if [ -n "$IN_NIX_SHELL" ] || [ -n "$NIX_PATH" ]; then
        if [ -n "$VIRTUAL_ENV" ]; then
            print_status "Virtual environment already active via Nix shell!"
            print_status "Installing/updating dependencies..."
            pip install --upgrade pip
            pip install -r requirements.txt
            return
        fi
    fi
    
    # Traditional venv setup for non-Nix environments
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_status "Virtual environment created"
    else
        print_warning "Virtual environment already exists"
    fi
    
    source venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    
    print_status "Python dependencies installed!"
}

# Test database setup
test_database() {
    print_step "Testing database setup..."
    
    source venv/bin/activate
    python3 -c "
import asyncio
from app.database import init_db
asyncio.run(init_db())
print('Database initialized successfully!')
    "
    
    print_status "Database test completed!"
}

# Display final instructions
show_instructions() {
    echo
    echo "🎉 Setup completed successfully!"
    echo "==============================="
    echo
    echo "Next steps:"
    echo
    if [ -n "$IN_NIX_SHELL" ] || [ -n "$NIX_PATH" ]; then
        echo "🔄 Nix Environment Detected:"
        echo "   Virtual environment is automatically managed!"
        echo "   Just run: python main.py"
        echo
    else
        echo "1. For local development:"
        echo "   source venv/bin/activate"
        echo "   python main.py"
        echo
    fi
    echo "2. For Docker deployment:"
    echo "   docker-compose up -d"
    echo
    echo "3. Access the application:"
    echo "   http://localhost:8000"
    echo
    echo "4. Create your first account and connect your Telegram!"
    echo
    echo "📚 For more information, see README.md"
    echo
}

# Main execution
main() {
    check_requirements
    setup_environment
    create_directories
    
    echo
    read -p "Do you want to set up Python virtual environment? (y/n): " setup_python
    if [[ $setup_python =~ ^[Yy]$ ]]; then
        setup_python_env
        test_database
    fi
    
    show_instructions
}

# Run main function
main "$@"
