from ..config import get_settings

settings = get_settings()

SECRET_KEY = settings.jwt_secret
ALGORITHM = "HS256"

# Validate the secret key
if not SECRET_KEY:
    raise ValueError(
        "JWT secret key is required. Add RC_JWT_SECRET to your .env file with a strong random value."
    )

if SECRET_KEY == "changeme-super-secret-key":
    raise ValueError(
        "JWT secret is still set to the default placeholder value. Please change it in your environment."
    )
