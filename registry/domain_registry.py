"""Central registry: action_name → domain instance."""


class DomainRegistry:
    _domains: dict = {}     # domain_id  → BaseDomain instance
    _action_map: dict = {}  # action_str → domain_id

    @classmethod
    def register(cls, domain):
        did = domain.get_id()
        cls._domains[did] = domain
        for action in domain.get_actions():
            cls._action_map[action] = did

    @classmethod
    def execute(cls, action: str, context, core_facade) -> dict:
        did = cls._action_map.get(action)
        if not did:
            raise ValueError(f"[DomainRegistry] No domain registered for action: {action!r}")
        return cls._domains[did].execute(action, context, core_facade)

    @classmethod
    def has_action(cls, action: str) -> bool:
        return action in cls._action_map

    @classmethod
    def get_all_actions(cls) -> list[str]:
        return list(cls._action_map.keys())

    @classmethod
    def get_domain(cls, domain_id: str):
        return cls._domains.get(domain_id)
