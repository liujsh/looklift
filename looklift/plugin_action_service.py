"""项目级 Plugin Action 查询、修改、确认与执行。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .capabilities import CapabilityGrantStore
from .plugin_actions import ActionError, PluginAction, PluginActionStore
from .plugin_connector_service import PluginConnectorService
from .plugin_registry import PluginRegistry
from .plugin_tools import PluginToolCatalog, PluginToolError, PluginToolGateway


class PluginActionServiceError(ValueError):
    """Action 请求未通过项目、revision、Schema 或执行边界。"""


class PluginActionService:
    """让 UI 操作持久化 Action，外部写入仍由统一网关执行。"""

    def __init__(
        self,
        *,
        action_store: PluginActionStore,
        plugin_registry: PluginRegistry,
        grant_store: CapabilityGrantStore,
        connector_service: PluginConnectorService,
    ) -> None:
        self._actions = action_store
        self._catalog = PluginToolCatalog(plugin_registry)
        self._grants = grant_store
        self._connectors = connector_service

    def list(self, *, project_id: str) -> tuple[dict[str, Any], ...]:
        try:
            return tuple(
                self._project(action)
                for action in self._actions.list(project_id=project_id)
            )
        except ActionError as exc:
            raise PluginActionServiceError(str(exc)) from exc

    def revise(
        self,
        action_id: str,
        *,
        project_id: str,
        expected_revision: int,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        self._validate_revision(expected_revision)
        if not isinstance(arguments, Mapping):
            raise PluginActionServiceError("Action 参数必须是对象")
        action = self._require_project(action_id, project_id)
        try:
            self._catalog.validate(action.plugin_identity, arguments)
            revised = self._actions.revise(
                action_id,
                arguments=arguments,
                expected_revision=expected_revision,
            )
        except (ActionError, PluginToolError) as exc:
            raise PluginActionServiceError(str(exc)) from exc
        return self._project(revised)

    def confirm_and_execute(
        self,
        action_id: str,
        *,
        project_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        self._validate_revision(expected_revision)
        action = self._require_project(action_id, project_id)
        try:
            self._catalog.validate(action.plugin_identity, action.arguments)
            confirmed = self._actions.confirm(
                action_id, expected_revision=expected_revision
            )
            gateway = PluginToolGateway(
                self._catalog,
                lambda tool, arguments: self._execute(
                    confirmed, tool, arguments
                ),
                action_store=self._actions,
            )
            gateway.execute_action(
                action_id,
                grants=tuple(grant for _, grant in self._grants.items()),
                current_account_id=confirmed.account_id,
            )
        except (ActionError, PluginToolError) as exc:
            raise PluginActionServiceError(str(exc)) from exc
        return self._project(self._actions.get(action_id))

    def reject(self, action_id: str, *, project_id: str) -> dict[str, Any]:
        self._require_project(action_id, project_id)
        try:
            return self._project(self._actions.reject(action_id))
        except ActionError as exc:
            raise PluginActionServiceError(str(exc)) from exc

    def cancel(self, action_id: str, *, project_id: str) -> dict[str, Any]:
        self._require_project(action_id, project_id)
        try:
            return self._project(self._actions.cancel(action_id))
        except ActionError as exc:
            raise PluginActionServiceError(str(exc)) from exc

    def _require_project(self, action_id: str, project_id: str) -> PluginAction:
        try:
            action = self._actions.get(action_id)
        except ActionError as exc:
            raise PluginActionServiceError(str(exc)) from exc
        if action.project_id != project_id:
            raise PluginActionServiceError("Action 不属于当前项目")
        return action

    def _project(self, action: PluginAction) -> dict[str, Any]:
        try:
            tool = self._catalog.resolve(action.plugin_identity)
            fields = [field.public_dict() for field in tool.confirmation_fields]
        except PluginToolError:
            # 历史 Action 仍需可审计；工具失效时只移除可编辑映射，执行路径继续拒绝。
            fields = []
        return {
            **action.public_dict(),
            "confirmation_fields": fields,
        }

    @staticmethod
    def _validate_revision(expected_revision: int) -> None:
        if (
            not isinstance(expected_revision, int)
            or isinstance(expected_revision, bool)
            or expected_revision < 1
        ):
            raise PluginActionServiceError("Action revision 无效")

    def _execute(
        self,
        action: PluginAction,
        tool,
        arguments: dict[str, Any],
    ) -> Mapping[str, Any]:
        return self._connectors.call_tool(
            plugin_name=tool.plugin_name,
            plugin_version=tool.plugin_version,
            service_name=tool.service,
            tool_name=tool.name,
            project_id=action.project_id,
            account_id=action.account_id,
            arguments=arguments,
        )
