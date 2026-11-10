"""Turn decoded websocket messages into tracker state changes."""

from collections.abc import Mapping

from .tracker_state import _id_key, _TrackerBase


class TrackerEvents(_TrackerBase):
    """Apply websocket event branches to tracked prompts."""

    async def handle_message(self, message: Mapping[str, object]) -> None:
        """Handle one decoded websocket message."""
        message_type = message.get("type")
        data = message.get("data")
        if not isinstance(message_type, str) or not isinstance(data, Mapping):
            return

        if message_type == "status":
            await self.poll_once(only_cancelling=True)
            return

        prompt_id = data.get("prompt_id")
        if not isinstance(prompt_id, str):
            return

        tracked = self._tracked.get(prompt_id)
        if tracked is None:
            return

        if message_type == "execution_start":
            await self._update_progress(tracked, status="in_progress")
            return

        if message_type == "execution_cached":
            cached = data.get("nodes")
            if isinstance(cached, list):
                tracked.cached = {item for item in cached if isinstance(item, str)}
            await self._update_progress(tracked)
            return

        if message_type == "executing":
            node = data.get("node")
            if isinstance(node, str):
                if tracked.running is not None and tracked.running != node:
                    tracked.completed.add(tracked.running)
                tracked.running = node
                await self._update_progress(tracked)
            elif node is None and tracked.running is not None:
                tracked.completed.add(tracked.running)
                tracked.running = None
            return

        if message_type == "progress_state":
            nodes = data.get("nodes")
            if isinstance(nodes, Mapping):
                running_nodes: list[str] = []
                for node_id, state in nodes.items():
                    if not isinstance(node_id, str) or not isinstance(state, Mapping):
                        continue

                    value = state.get("value")
                    maximum = state.get("max")
                    if isinstance(value, (int, float)) and isinstance(maximum, (int, float)):
                        tracked.progress[node_id] = (float(value), float(maximum))

                    state_name = state.get("state")
                    if state_name in ("finished", "error"):
                        tracked.completed.add(node_id)
                        if tracked.running == node_id:
                            tracked.running = None
                    elif state_name == "running":
                        running_nodes.append(node_id)

                if running_nodes and tracked.running not in running_nodes:
                    tracked.running = min(running_nodes, key=_id_key)

            await self._update_progress(tracked)
            return

        if message_type == "progress":
            node = data.get("node")
            value = data.get("value")
            maximum = data.get("max")
            if (
                isinstance(node, str)
                and isinstance(value, (int, float))
                and isinstance(maximum, (int, float))
            ):
                tracked.progress[node] = (float(value), float(maximum))
                if node not in tracked.completed:
                    tracked.running = node
                await self._update_progress(tracked)
            return

        if message_type == "execution_success":
            await self._finish_prompt(tracked)
            return

        if message_type == "execution_error":
            node_type = data.get("node_type")
            exception_message = data.get("exception_message")
            text = "workflow execution failed"
            if isinstance(node_type, str) and isinstance(exception_message, str):
                text = f"{node_type}: {exception_message}"
            elif isinstance(exception_message, str):
                text = exception_message
            await self._fail_prompt(tracked, text)
            return

        if message_type == "execution_interrupted":
            await self._cancel_prompt(tracked)
