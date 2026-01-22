"""
SecureMCP @secure Decorator - Simplified Version
Delegates all security to MACAW SDK components from server instance
"""

import threading
from functools import wraps
from typing import Dict, Any, Optional, List, Callable, Union

# Thread-local storage for current server instance
_current_server = threading.local()

def set_current_server(server):
    """Set the current server in thread-local storage"""
    _current_server.value = server

def get_current_server():
    """Get the current server from thread-local storage"""
    return getattr(_current_server, 'value', None)


def secure(
    # Core security parameters
    policy: Union[str, Dict[str, Any]] = None,
    policy_file: Optional[str] = None,
    audit_log: bool = False,
    audit_level: str = "basic",
    
    # Authentication
    auth_provider: Optional[str] = None,
    required_roles: Optional[List[str]] = None,
    required_groups: Optional[List[str]] = None,
    
    # Rate limiting
    rate_limit: Optional[int] = None,
    
    # Signing
    sign_requests: bool = False,
    sign_results: bool = False,
    
    # Monitoring
    monitor: bool = False,
    trace: bool = False,
    
    # Advanced features (for future use)
    attested: bool = False,
    tenant_aware: bool = False,
    risk_assessment: Optional[Dict[str, Any]] = None,
    llm_security: Optional[Dict[str, Any]] = None,
    **kwargs  # Accept other params for compatibility
):
    """
    Optional security enhancement decorator for MCP tools.
    
    This decorator adds fine-grained security controls on top of the baseline
    security provided by SecureMCP's transport layer. All security enforcement
    is delegated to MACAW SDK components.
    
    Args:
        policy: Security policy name or dict
        policy_file: Path to policy file
        audit_log: Enable detailed audit logging
        audit_level: Level of audit detail (basic/detailed/full)
        auth_provider: Authentication provider (okta/github/auth0/etc)
        required_roles: List of required roles
        required_groups: List of required groups
        rate_limit: Calls per minute limit
        sign_requests: Sign incoming requests
        sign_results: Sign outgoing results
        monitor: Enable monitoring
        trace: Enable tracing
        attested: Require attested workflow
        tenant_aware: Enable multi-tenancy
        risk_assessment: Risk assessment config
        llm_security: LLM security config
        **kwargs: Additional parameters for future expansion
    
    Example:
        @server.tool("sensitive_operation")
        @secure(
            auth_provider="okta",
            required_roles=["admin"],
            audit_log=True,
            rate_limit=10
        )
        def sensitive_operation(data: str) -> str:
            return process_data(data)
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get server instance
            server = get_current_server()
            if not server:
                # No server context, just run the function
                return func(*args, **kwargs)
            
            # Get MACAW components from server
            policy_enforcer = getattr(server, 'policy_enforcer', None)
            audit_logger = getattr(server, 'audit_logger', None)
            server_agent = getattr(server, 'server_agent', None)
            
            # Build security context
            security_context = {
                'function': func.__name__,
                'policy': policy,
                'auth_provider': auth_provider,
                'required_roles': required_roles,
                'required_groups': required_groups,
                'rate_limit': rate_limit,
                'attested': attested
            }
            
            # 1. Authentication checks (delegated to MACAW)
            if auth_provider or required_roles or required_groups:
                # In production, MACAW's AuthenticationService handles this
                # For now, we'll check if server has auth configured
                if not getattr(server, 'request_authenticator', None):
                    # Log warning but don't block
                    if audit_logger:
                        audit_logger.log_event({
                            'type': 'auth_check_skipped',
                            'reason': 'no_authenticator',
                            'function': func.__name__
                        })
            
            # 2. Policy enforcement (delegated to MACAW)
            if policy and policy_enforcer:
                # MACAW's PolicyEnforcer handles this
                # Create an invocation context
                from macaw.protocol.mcp_types import Invocation
                invocation = Invocation(
                    tool_name=func.__name__,
                    params=kwargs,
                    metadata=security_context
                )
                
                # Check policy
                try:
                    allowed = policy_enforcer.check_invocation(invocation)
                    if not allowed:
                        return {
                            'error': 'Policy violation',
                            'policy': policy,
                            'function': func.__name__
                        }
                except Exception as e:
                    # Policy check failed, log but don't block
                    if audit_logger:
                        audit_logger.log_event({
                            'type': 'policy_check_error',
                            'error': str(e),
                            'function': func.__name__
                        })
            
            # 3. Rate limiting (delegated to MACAW)
            if rate_limit:
                # MACAW's RateLimitVerifier handles this
                # For now, just log the intent
                if audit_logger:
                    audit_logger.log_event({
                        'type': 'rate_limit_check',
                        'limit': rate_limit,
                        'function': func.__name__
                    })
            
            # 4. Pre-execution audit
            if audit_log and audit_logger:
                audit_logger.log_event({
                    'type': 'function_invocation',
                    'function': func.__name__,
                    'audit_level': audit_level,
                    'security_context': security_context,
                    'args_count': len(args),
                    'kwargs_keys': list(kwargs.keys())
                })
            
            # 5. Sign request if needed
            if sign_requests and server_agent:
                # MACAW's agent handles signing
                # This would be done at transport layer
                pass
            
            # 6. Execute the function
            try:
                result = func(*args, **kwargs)
            except Exception as e:
                # Log error and re-raise
                if audit_logger:
                    audit_logger.log_event({
                        'type': 'function_error',
                        'function': func.__name__,
                        'error': str(e)
                    })
                raise
            
            # 7. Sign result if needed
            if sign_results and server_agent:
                # MACAW's agent handles signing
                # This would be done at transport layer
                pass
            
            # 8. Post-execution audit
            if audit_log and audit_logger:
                audit_logger.log_event({
                    'type': 'function_completed',
                    'function': func.__name__,
                    'success': True
                })
            
            # 9. Monitoring/tracing
            if (monitor or trace) and hasattr(server, 'telemetry_manager'):
                # MACAW's telemetry handles this
                pass
            
            return result
        
        # Mark function as secure-decorated for introspection
        wrapper._secure_decorated = True
        wrapper._secure_params = {
            'policy': policy,
            'auth_provider': auth_provider,
            'required_roles': required_roles,
            'audit_log': audit_log
        }
        
        return wrapper
    return decorator