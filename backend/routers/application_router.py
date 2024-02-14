import logging

import jwt
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from models.dto.application_dto import ApplicationDTO
from models.enum.user_roles import User_roles
from services.classroom_service import ClassroomService
from storage.db_config import get_db


from services.user_service import UserService
from services.auth_service import AuthService
from services.application_service import ApplicationService
from datetime import timedelta

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

application_router = APIRouter(prefix="/applications")


@application_router.post(
    "/create/",
    responses={
        201: {
            "description": "Request created successfully"
        },
        400: {
            "description": "Bad request data"
        },
        500: {
            "description": "Internal server error"
        }
    }
)
async def create_application(
                application_DTO: ApplicationDTO,
                access_token: str = Depends(config.oauth2_scheme),
                db: Session = Depends(get_db),
                user_service: UserService = Depends(UserService),
                application_service: ApplicationService = Depends(ApplicationService),
                auth_service: AuthService = Depends(AuthService),
                classroom_service: ClassroomService = Depends(ClassroomService)
                ):
    try:
        if await auth_service.check_revoked(db, access_token):
            logger.warning(f"(Create application) Token is revoked: {access_token}")
            raise HTTPException(status_code=403, detail="Token revoked")

        token_data = auth_service.get_data_from_access_token(access_token)
        user = await user_service.get_user_by_id(db, (await token_data)["sub"])

        if await classroom_service.check_correct_classroom(db, str(application_DTO.classroom_id)):
            raise HTTPException(status_code=404, detail="classroom not found")

        if await application_service.time_table_id_validate(db, application_DTO.time_table_id):
            raise HTTPException(status_code=404, detail="time not found")

        role = user.role_id
        if role == User_roles.Student:
            if application_DTO.dublicates > 1:
                raise HTTPException(status_code=400, detail="you can't do a lot of gublicates")

            if await application_service.check_priority(
                db,
                application_DTO.classroom_id,
                application_DTO.class_date,
                application_DTO.time_table_id
            ):
                raise HTTPException(status_code=403, detail="teacher has already occupied this classroom")
        else:
            await application_service.delete_all_students(
                db,
                application_DTO.classroom_id,
                application_DTO.class_date,
                application_DTO.time_table_id
            )

        for i in range (application_DTO.dublicates):
            application_DTO.class_date += (timedelta(days=config.ONE_WEEK)*(i))
            await application_service.create_application(user.id, application_DTO, db)

    except jwt.PyJWTError as e:
        logger.warning(f"(Create application) Bad token: {e}")
        raise HTTPException(status_code=403, detail="Bad token")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"(Application) Error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")