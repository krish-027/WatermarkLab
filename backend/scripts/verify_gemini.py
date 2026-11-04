r"""One opt-in real Gemini request. Only sanitized usage metadata is retained.

Run from backend: .\.venv\Scripts\python.exe scripts/verify_gemini.py --live
Never print provider exception details, credentials, source or output.
"""
import argparse
import asyncio
import json
import logging
from pathlib import Path
import sys
from datetime import datetime, timezone

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.core.config import Settings
from app.schemas.transformation import TransformInput
from app.services.gemini_service import GeminiService, GeminiFailure

async def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live',action='store_true',help='Authorize exactly one paid synthetic-text request')
    args=parser.parse_args()
    if not args.live: parser.error('Explicit --live required; this can use paid quota.')
    logging.disable(logging.CRITICAL)
    service=GeminiService(Settings())
    report={'timestamp':datetime.now(timezone.utc).isoformat(),'verification':'direct service / real Google API','attempts':0,'automatic_retries':0}
    if service.capabilities()['status']!='configured':
        report.update(status='setup required')
    else:
        report['attempts']=1
        try:
            result=await service.transform(TransformInput(text='A researcher watered two seedlings daily and measured their growth for one week.',external_processing_consent=True))
            assert result.transformed_text.strip() and result.provenance=='UNKNOWN'
            report.update(status='passed',model=result.model,model_version=result.model_version,
                source_characters=result.source_characters,output_characters=result.output_characters,
                usage=result.usage.model_dump(),execution_ms=result.execution_ms)
        except GeminiFailure as error:
            report.update(status='failed',safe_error_code=error.code,usage='Unavailable; provider may have consumed tokens.')
        except Exception:
            report.update(status='failed',safe_error_code='LOCAL_VERIFICATION_ERROR')
    target=Path('.cache/phase6_live_service.json')
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':
    sys.exit(asyncio.run(main()))
