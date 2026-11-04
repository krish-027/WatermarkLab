"""Create a local FastAPI process without model or external-service dependencies."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from jwt import PyJWKClient
from app.api.routes.accounts import router as accounts_router
from app.api.routes.analysis import router as analysis_router
from app.api.routes.transformations import router as transformations_router
from app.services.gemini_service import GeminiService
from app.api.routes.robustness import router as robustness_router
from app.api.routes.robustness_saves import router as robustness_saves_router
from app.watermark.kgw_adapter import KGWAdapter
from app.watermark.synthid_adapter import SynthIDAdapter
from app.core.analysis_limits import AnalysisBodyLimit
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.responses import JSONResponse

from app.api.routes.health import router as health_router
from app.core.config import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    application = FastAPI(
        title='WatermarkLab API',
        version='0.2.0',
        description=(
            'Local application foundation. Health reports API liveness only. '
            'User metadata, ephemeral watermark research analysis and consented Gemini transformations require verified Supabase access tokens.'
        ),
    )
    application.state.settings = settings
    application.state.kgw = KGWAdapter()
    application.state.synthid = SynthIDAdapter()
    application.state.gemini = GeminiService(settings)
    application.add_middleware(AnalysisBodyLimit)

    @application.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        if request.url.path in ('/api/v1/analyze','/api/v1/transform','/api/v1/compare','/api/v1/robustness/runs'):
            # FastAPI's default echoes invalid input, including submitted raw text.
            message='Invalid transformation request. Check text, operation, objective and external-processing consent.' if request.url.path=='/api/v1/transform' else 'Invalid analysis request. Check text, method, profile and size limits.'
            return JSONResponse({'detail': message}, status_code=422)
        return await request_validation_exception_handler(request, error)
    application.state.jwks = PyJWKClient(settings.supabase_url + '/auth/v1/.well-known/jwks.json', lifespan=300, timeout=10) if settings.supabase_url else None
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
        allow_headers=['Accept', 'Content-Type', 'Authorization'],
    )
    application.include_router(health_router)
    application.include_router(accounts_router)
    application.include_router(analysis_router)
    application.include_router(transformations_router)
    application.include_router(robustness_router)
    application.include_router(robustness_saves_router)
    return application


app = create_app()
