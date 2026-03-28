#!/bin/bash

set -e

echo "=== Database Setup Script ==="

# Detect OS
if [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macOS"
    PACKAGE_MANAGER="brew"
    SERVICE_CMD="brew services"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="Linux"
    PACKAGE_MANAGER="apt"
    SERVICE_CMD="sudo systemctl"
else
    echo "❌ Unsupported OS: $OSTYPE"
    exit 1
fi

echo "Detected OS: $OS"

# Check if PostgreSQL is installed
if command -v psql &> /dev/null; then
    echo "✅ PostgreSQL already installed."
else
    echo "📦 Installing PostgreSQL..."
    if [[ "$OS" == "macOS" ]]; then
        if ! command -v brew &> /dev/null; then
            echo "❌ Homebrew not found. Please install Homebrew first."
            exit 1
        fi
        brew install postgresql
    else
        sudo apt update
        sudo apt install -y postgresql postgresql-contrib
    fi
    echo "✅ PostgreSQL installed."
fi

# Start PostgreSQL service
echo "🚀 Starting PostgreSQL service..."
if [[ "$OS" == "macOS" ]]; then
    brew services start postgresql
else
    sudo systemctl start postgresql
    sudo systemctl enable postgresql
fi
echo "✅ PostgreSQL service started."

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL to be ready..."
sleep 5

# Generate secure password
PASSWORD=$(openssl rand -base64 12 | tr -d "=+/" | cut -c1-16)
echo "🔐 Generated secure password for user 'anjal'"

# Create user and database
echo "👤 Creating PostgreSQL user 'anjal'..."
if [[ "$OS" == "macOS" ]]; then
    if psql postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='anjal'" | grep -q 1; then
        echo "⚠️  User 'anjal' already exists. Skipping user creation."
    else
        psql postgres -c "CREATE USER anjal WITH PASSWORD '$PASSWORD';"
        echo "✅ User 'anjal' created."
    fi

    echo "🗄️  Creating database 'research_agent'..."
    if psql postgres -tAc "SELECT 1 FROM pg_database WHERE datname='research_agent'" | grep -q 1; then
        echo "⚠️  Database 'research_agent' already exists. Skipping database creation."
    else
        psql postgres -c "CREATE DATABASE research_agent OWNER anjal;"
        echo "✅ Database 'research_agent' created."
    fi
else
    # Linux
    if sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='anjal'" | grep -q 1; then
        echo "⚠️  User 'anjal' already exists. Skipping user creation."
    else
        sudo -u postgres psql -c "CREATE USER anjal WITH PASSWORD '$PASSWORD';"
        echo "✅ User 'anjal' created."
    fi

    echo "🗄️  Creating database 'research_agent'..."
    if sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='research_agent'" | grep -q 1; then
        echo "⚠️  Database 'research_agent' already exists. Skipping database creation."
    else
        sudo -u postgres psql -c "CREATE DATABASE research_agent OWNER anjal;"
        echo "✅ Database 'research_agent' created."
    fi
fi

# Run Python script to create tables
echo "📋 Creating database tables..."
source venv/bin/activate
pip install psycopg2-binary
python init_db.py "$PASSWORD"
echo "✅ Database tables created."

# Update .env file
ENV_FILE=".env"
DSN="postgresql://anjal:$PASSWORD@localhost:5432/research_agent"

if [[ -f "$ENV_FILE" ]]; then
    if grep -q "^POSTGRES_DSN=" "$ENV_FILE"; then
        echo "🔄 Updating existing POSTGRES_DSN in .env..."
        sed -i.bak "s|^POSTGRES_DSN=.*|POSTGRES_DSN=$DSN|" "$ENV_FILE"
        rm "${ENV_FILE}.bak"
    else
        echo "➕ Adding POSTGRES_DSN to existing .env..."
        echo "POSTGRES_DSN=$DSN" >> "$ENV_FILE"
    fi
else
    echo "📝 Creating .env file with POSTGRES_DSN..."
    echo "POSTGRES_DSN=$DSN" > "$ENV_FILE"
fi

echo "✅ .env file updated."
echo ""
echo "🎉 Database setup complete!"
echo "   User: anjal"
echo "   Database: research_agent"
echo "   DSN: $DSN"
echo ""
echo "⚠️  IMPORTANT: Save this password securely:"
echo "   Password: $PASSWORD"