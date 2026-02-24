from strawberry.fastapi import GraphQLRouter

from app.api.dependencies import get_graphql_context
from app.core.config import settings
from app.graphql.schema import schema

ide_setting = "graphiql" if settings.ENVIRONMENT != "production" else None
router = GraphQLRouter(
    schema,
    context_getter=get_graphql_context,
    graphql_ide=ide_setting,
    allow_queries_via_get=settings.ENVIRONMENT != "production",
    keep_alive=True,
    keep_alive_interval=float(settings.GRAPHQL_WS_KEEP_ALIVE_INTERVAL_SECONDS),
    subscription_protocols=("graphql-transport-ws",),
)
