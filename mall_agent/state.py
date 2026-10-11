from typing import TypedDict, Annotated, List, Optional
from langchain_core.messages import BaseMessage
from operator import add


class AgentState(TypedDict, total=False):
    messages: Annotated[List[BaseMessage], add]
    user_intent: Optional[str]
    user_location: Optional[str]
    user_destination: Optional[str]
    user_route_from: Optional[str]
    user_route_to: Optional[str]
    user_preference: Optional[str]
    needs: Optional[List[str]]
    mall_results: Optional[str]
    hotel_results: Optional[str]
    sight_results: Optional[str]
    route_results: Optional[str]
    final_response: Optional[str]
    user_docs: Optional[str]
    user_image: Optional[str]
    image_desc: Optional[str]
