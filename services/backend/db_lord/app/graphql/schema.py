import strawberry
from strawberry.extensions import MaxAliasesLimiter, MaxTokensLimiter, QueryDepthLimiter

from app.graphql.resolvers import Query, Subscription

schema = strawberry.Schema(
    query=Query,
    subscription=Subscription,
    extensions=[
        QueryDepthLimiter(max_depth=8),  # Prevent deeply nested queries
        MaxTokensLimiter(max_token_count=5000),  # Prevent huge queries
        MaxAliasesLimiter(max_alias_count=15),  # Prevent alias-based DoS
    ],
)
