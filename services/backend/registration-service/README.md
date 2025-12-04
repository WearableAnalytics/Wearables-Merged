# RegistrationService
This is the first draft of a **Registration Service**, which is not gold standard secure, but on a way to have a solid 
level of security.

---
### Quick Start

Set in `/app` the environments variables properly:
```
# Example
POSTGRES_USER=test
POSTGRES_PASSWORD=password
POSTGRES_DB=db

DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres/${POSTGRES_DB}
CHARITE_URL=http://localhost:9090
SECRET_KEY=secret
TOKEN_EXPIRATION=900

# Mail-Config
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SENDER_EMAIL=example@gmail.com
APP_PASSWORD=pass word uidf sfgf
```

Please also set in `/keycloak` the environment variables:
```
# Example
POSTGRES_DB=keycloak
POSTGRES_USER=keycloak
POSTGRES_PASSWORD=password

KC_DB=postgres
KC_DB_URL=jdbc:postgresql://keycloak-postgres:5432/keycloak
KC_DB_USERNAME=${POSTGRES_USER:-keycloak}
KC_DB_PASSWORD=${POSTGRES_PASSWORD:-password}
KC_HOSTNAME=localhost
KC_HOSTNAME_PORT=7070
KC_HOSTNAME_STRICT=false
KC_HOSTNAME_STRICT_HTTPS=false
KC_LOG_LEVEL=info
KC_METRICS_ENABLED=true
KC_HEALTH_ENABLED=true
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=password
```

**After having all environment variables set, you can just execute following command**:

```shell
just up
```
This will spin up all necessary containers (test-database, service, and keycloak).
**Please wait couple seconds until all services are healthy and able to serve requests**.

To check whether everything worked fine please call this [Link](http://localhost:8000/)

---
