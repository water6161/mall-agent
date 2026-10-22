import base64
from langchain_core.messages import HumanMessage, AIMessage

from .graph import build_graph
from .doc_parser import parse_files
from .tools.map_render import extract_points


class MallAgent:
    def __init__(self):
        self.graph = build_graph()

    def chat(self, user_input: str, history: list | None = None,
             file_paths: list | None = None, image_path: str | None = None) -> tuple[str, list]:
        messages = []
        if history:
            for item in history:
                if isinstance(item, dict):
                    role = item.get("role", "")
                    content = item.get("content", "")
                elif isinstance(item, (tuple, list)) and len(item) == 2:
                    role, content = item
                else:
                    continue
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role == "assistant":
                    messages.append(AIMessage(content=content))

        messages.append(HumanMessage(content=user_input))

        messages = messages[-13:]

        initial_state: dict = {"messages": messages}

        if file_paths:
            docs_text = parse_files(file_paths)
            initial_state["user_docs"] = docs_text

        if image_path:
            initial_state["user_image"] = image_path

        result = self.graph.invoke(initial_state)

        reply = result.get("final_response")
        if not reply and result.get("messages"):
            reply = result["messages"][-1].content
        reply = reply or "抱歉，我没能给出有效回复。"

        points = extract_points(
            result.get("mall_results") or "",
            result.get("hotel_results") or "",
            result.get("sight_results") or "",
        )
        return reply, points
