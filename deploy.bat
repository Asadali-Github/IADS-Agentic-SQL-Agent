@echo off
REM Deployment script for IADS Agentic SQL Agent (Windows)
REM Usage: deploy.bat [environment] [action]
REM Example: deploy.bat production up

setlocal enabledelayedexpansion

set ENVIRONMENT=%1
set ACTION=%2

if "%ENVIRONMENT%"=="" set ENVIRONMENT=development
if "%ACTION%"=="" set ACTION=up

echo.
echo ========================================
echo 🚀 IADS Agentic SQL Agent Deployment
echo ========================================
echo Environment: %ENVIRONMENT%
echo Action: %ACTION%
echo.

REM Check prerequisites
echo Checking prerequisites...

docker --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker is not installed
    exit /b 1
)

docker-compose --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Docker Compose is not installed
    exit /b 1
)

echo ✅ Docker and Docker Compose found
echo.

REM Validate environment
echo Validating environment configuration...

set ENV_FILE=.env.%ENVIRONMENT%

if not exist "%ENV_FILE%" (
    echo ❌ %ENV_FILE% not found
    echo Create it using: copy .env.%ENVIRONMENT%.example %ENV_FILE%
    exit /b 1
)

echo ✅ Environment configuration is valid
echo.

REM Execute action
if "%ACTION%"=="up" goto START
if "%ACTION%"=="start" goto START
if "%ACTION%"=="down" goto STOP
if "%ACTION%"=="stop" goto STOP
if "%ACTION%"=="restart" goto RESTART
if "%ACTION%"=="logs" goto LOGS
if "%ACTION%"=="health" goto HEALTH

echo Usage: %0 [environment] [action]
echo.
echo Environments:
echo   development  (default)
echo   production
echo.
echo Actions:
echo   up           Start services (builds if needed)
echo   down         Stop services
echo   restart      Restart services
echo   logs         View logs
echo   health       Health check
exit /b 1

:START
echo Building Docker images...
docker-compose -f docker-compose.prod.yml build --no-cache
if errorlevel 1 (
    echo ❌ Failed to build images
    exit /b 1
)

echo ✅ Docker images built
echo.
echo Starting services...
docker-compose -f docker-compose.prod.yml up -d
if errorlevel 1 (
    echo ❌ Failed to start services
    exit /b 1
)

echo ✅ Services started
echo.
echo Service Status:
docker-compose -f docker-compose.prod.yml ps
echo.
echo Services are running:
echo   📊 API: http://localhost:8000
echo   💬 Frontend: http://localhost:8501
echo   📈 Monitoring: http://localhost:8502
echo.
timeout /t 5 /nobreak >nul
goto HEALTH

:STOP
echo Stopping services...
docker-compose -f docker-compose.prod.yml down
if errorlevel 1 (
    echo ❌ Failed to stop services
    exit /b 1
)

echo ✅ Services stopped
goto END

:RESTART
echo Stopping services...
docker-compose -f docker-compose.prod.yml down
timeout /t 2 /nobreak >nul
echo Starting services...
docker-compose -f docker-compose.prod.yml up -d
timeout /t 5 /nobreak >nul
goto HEALTH

:LOGS
echo Showing logs...
docker-compose -f docker-compose.prod.yml logs -f --tail=100
goto END

:HEALTH
echo Performing health checks...

echo Checking API...
curl -s http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo ❌ API is not responding
) else (
    echo ✅ API is healthy
)

echo Checking Frontend...
curl -s http://localhost:8501 >nul 2>&1
if errorlevel 1 (
    echo ❌ Frontend is not responding
) else (
    echo ✅ Frontend is running
)

echo Checking Monitoring...
curl -s http://localhost:8502 >nul 2>&1
if errorlevel 1 (
    echo ❌ Monitoring dashboard is not responding
) else (
    echo ✅ Monitoring dashboard is running
)

:END
echo.
echo Done!
echo.
