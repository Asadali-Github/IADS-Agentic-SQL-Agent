#!/bin/bash
# Deployment script for IADS Agentic SQL Agent
# Usage: ./deploy.sh [environment] [action]
# Example: ./deploy.sh production up

set -e

ENVIRONMENT=${1:-development}
ACTION=${2:-up}

echo "🚀 IADS Agentic SQL Agent Deployment"
echo "Environment: $ENVIRONMENT"
echo "Action: $ACTION"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check prerequisites
check_prerequisites() {
    echo -e "\n${YELLOW}Checking prerequisites...${NC}"
    
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker is not installed${NC}"
        exit 1
    fi
    
    if ! command -v docker-compose &> /dev/null; then
        echo -e "${RED}❌ Docker Compose is not installed${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Docker and Docker Compose found${NC}"
}

# Validate environment
validate_environment() {
    echo -e "\n${YELLOW}Validating environment configuration...${NC}"
    
    ENV_FILE=".env.${ENVIRONMENT}"
    
    if [ ! -f "$ENV_FILE" ]; then
        echo -e "${RED}❌ $ENV_FILE not found${NC}"
        echo "Create it using: cp .env.${ENVIRONMENT}.example $ENV_FILE"
        exit 1
    fi
    
    # Check critical variables
    if ! grep -q "ADB_PASSWORD" "$ENV_FILE"; then
        echo -e "${RED}❌ Missing ADB_PASSWORD in $ENV_FILE${NC}"
        exit 1
    fi
    
    if ! grep -q "OCI_CONFIG_PATH" "$ENV_FILE"; then
        echo -e "${RED}❌ Missing OCI_CONFIG_PATH in $ENV_FILE${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✅ Environment configuration is valid${NC}"
}

# Build images
build_images() {
    echo -e "\n${YELLOW}Building Docker images...${NC}"
    
    COMPOSE_FILE="docker-compose.prod.yml"
    docker-compose -f "$COMPOSE_FILE" build --no-cache
    
    echo -e "${GREEN}✅ Docker images built${NC}"
}

# Start services
start_services() {
    echo -e "\n${YELLOW}Starting services...${NC}"
    
    COMPOSE_FILE="docker-compose.prod.yml"
    docker-compose -f "$COMPOSE_FILE" up -d
    
    echo -e "${GREEN}✅ Services started${NC}"
    
    # Show service status
    echo -e "\n${YELLOW}Service Status:${NC}"
    docker-compose -f "$COMPOSE_FILE" ps
    
    # Show URLs
    echo -e "\n${GREEN}Services are running:${NC}"
    echo "  📊 API: http://localhost:8000"
    echo "  💬 Frontend: http://localhost:8501"
    echo "  📈 Monitoring: http://localhost:8502"
}

# Stop services
stop_services() {
    echo -e "\n${YELLOW}Stopping services...${NC}"
    
    COMPOSE_FILE="docker-compose.prod.yml"
    docker-compose -f "$COMPOSE_FILE" down
    
    echo -e "${GREEN}✅ Services stopped${NC}"
}

# Health check
health_check() {
    echo -e "\n${YELLOW}Performing health checks...${NC}"
    
    # Check API
    if curl -s http://localhost:8000/health > /dev/null; then
        echo -e "${GREEN}✅ API is healthy${NC}"
    else
        echo -e "${RED}❌ API is not responding${NC}"
        return 1
    fi
    
    # Check Frontend
    if curl -s http://localhost:8501 > /dev/null; then
        echo -e "${GREEN}✅ Frontend is running${NC}"
    else
        echo -e "${RED}❌ Frontend is not responding${NC}"
        return 1
    fi
    
    # Check Monitoring
    if curl -s http://localhost:8502 > /dev/null; then
        echo -e "${GREEN}✅ Monitoring dashboard is running${NC}"
    else
        echo -e "${RED}❌ Monitoring dashboard is not responding${NC}"
        return 1
    fi
}

# View logs
view_logs() {
    echo -e "\n${YELLOW}Showing logs...${NC}"
    
    COMPOSE_FILE="docker-compose.prod.yml"
    docker-compose -f "$COMPOSE_FILE" logs -f --tail=100
}

# Main execution
case $ACTION in
    up|start)
        check_prerequisites
        validate_environment
        build_images
        start_services
        sleep 5
        health_check
        ;;
    down|stop)
        stop_services
        ;;
    restart)
        stop_services
        sleep 2
        start_services
        sleep 5
        health_check
        ;;
    logs)
        view_logs
        ;;
    health)
        health_check
        ;;
    *)
        echo "Usage: $0 [environment] [action]"
        echo ""
        echo "Environments:"
        echo "  development  (default)"
        echo "  production"
        echo ""
        echo "Actions:"
        echo "  up           Start services (builds if needed)"
        echo "  down         Stop services"
        echo "  restart      Restart services"
        echo "  logs         View logs"
        echo "  health       Health check"
        exit 1
        ;;
esac

echo -e "\n${GREEN}Done!${NC}\n"
