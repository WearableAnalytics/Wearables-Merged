from strawberry.fastapi import GraphQLRouter

from app.api.dependencies import get_graphql_context
from app.graphql.schema import schema

router = GraphQLRouter(
    schema,
    context_getter=get_graphql_context,
    graphql_ide="graphiql",
)
