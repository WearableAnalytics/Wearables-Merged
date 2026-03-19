import strawberry
from strawberry.extensions import MaxAliasesLimiter, MaxTokensLimiter, QueryDepthLimiter
from strawberry.schema.config import StrawberryConfig

from app.core.config import settings
from app.graphql.resolvers import Query, Subscription

schema = strawberry.Schema(
    query=Query,
    subscription=Subscription,
    config=StrawberryConfig(relay_max_results=settings.GRAPHQL_RELAY_MAX_RESULTS),
    extensions=[
        QueryDepthLimiter(max_depth=settings.GRAPHQL_MAX_DEPTH),
        MaxTokensLimiter(max_token_count=settings.GRAPHQL_MAX_TOKENS),
        MaxAliasesLimiter(max_alias_count=settings.GRAPHQL_MAX_ALIASES),
    ],
)
