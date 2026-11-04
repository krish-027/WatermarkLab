from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from app.core.security import Identity, require_user
from app.schemas.transformation import TransformInput, TransformResult
from app.services.gemini_service import GeminiFailure

router=APIRouter(prefix='/api/v1',tags=['Gemini transformations'])

@router.get('/transform/capabilities')
def capabilities(request:Request):
    return request.app.state.gemini.capabilities()

@router.post('/transform',response_model=TransformResult)
async def transform(payload:TransformInput,request:Request,response:Response,user:Identity=Depends(require_user)):
    response.headers['Cache-Control']='no-store'
    try: return await request.app.state.gemini.transform(payload)
    except GeminiFailure as error:
        return JSONResponse(status_code=error.status,
            content={'detail':{'code':error.code,'message':error.message,'retryable':error.retryable}},
            headers={'Cache-Control':'no-store',**({'Retry-After':'5'} if error.status==429 else {})})
