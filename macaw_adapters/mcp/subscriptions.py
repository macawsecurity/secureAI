"""
Resource Subscriptions for SecureMCP

Enables clients to subscribe to resource changes and receive real-time updates.
When MACAW is available, updates are signed for authenticity.
"""

import asyncio
import logging
import uuid
from typing import Dict, Any, List, Callable, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class SubscriptionEvent(Enum):
    """Types of subscription events"""
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    ERROR = "error"


@dataclass
class Subscription:
    """Represents a resource subscription"""
    subscription_id: str
    client_id: str
    resource_uri: str
    created_at: datetime
    last_update: Optional[datetime] = None
    event_types: Set[SubscriptionEvent] = field(default_factory=lambda: {SubscriptionEvent.UPDATED})
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def matches_event(self, event_type: SubscriptionEvent) -> bool:
        """Check if subscription should receive this event type"""
        return event_type in self.event_types


@dataclass 
class ResourceUpdate:
    """Represents a resource update event"""
    resource_uri: str
    event_type: SubscriptionEvent
    data: Any
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    signature: Optional[str] = None  # Signature when MACAW available
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for transmission"""
        return {
            "resource_uri": self.resource_uri,
            "event_type": self.event_type.value,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
            "signature": self.signature
        }


class SubscriptionManager:
    """
    Manages resource subscriptions for a SecureMCP server.
    
    This class handles:
    - Subscription registration/unregistration
    - Event distribution to subscribers
    - Subscription lifecycle management
    """
    
    def __init__(self, server=None):
        """
        Initialize subscription manager.
        
        Args:
            server: SecureMCP Server instance
        """
        self.server = server
        self.subscriptions: Dict[str, Subscription] = {}
        self.resource_subscriptions: Dict[str, List[str]] = {}  # resource_uri -> subscription_ids
        self.client_subscriptions: Dict[str, List[str]] = {}  # client_id -> subscription_ids
        self.update_handlers: Dict[str, Callable] = {}  # client_id -> handler function
        
        logger.info("SubscriptionManager initialized")
    
    async def subscribe(
        self,
        client_id: str,
        resource_uri: str,
        event_types: Optional[List[SubscriptionEvent]] = None,
        handler: Optional[Callable] = None
    ) -> str:
        """
        Subscribe a client to resource updates.
        
        Args:
            client_id: ID of subscribing client
            resource_uri: URI pattern of resource to subscribe to
            event_types: Types of events to subscribe to
            handler: Callback function for updates
            
        Returns:
            Subscription ID
        """
        subscription_id = f"sub-{uuid.uuid4().hex[:8]}"
        
        # Create subscription
        subscription = Subscription(
            subscription_id=subscription_id,
            client_id=client_id,
            resource_uri=resource_uri,
            created_at=datetime.now(),
            event_types=set(event_types) if event_types else {SubscriptionEvent.UPDATED}
        )
        
        # Store subscription
        self.subscriptions[subscription_id] = subscription
        
        # Index by resource
        if resource_uri not in self.resource_subscriptions:
            self.resource_subscriptions[resource_uri] = []
        self.resource_subscriptions[resource_uri].append(subscription_id)
        
        # Index by client
        if client_id not in self.client_subscriptions:
            self.client_subscriptions[client_id] = []
        self.client_subscriptions[client_id].append(subscription_id)
        
        # Store handler if provided
        if handler:
            self.update_handlers[client_id] = handler
        
        logger.info(f"Client {client_id} subscribed to {resource_uri}: {subscription_id}")
        
        return subscription_id
    
    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from resource updates.
        
        Args:
            subscription_id: ID of subscription to remove
            
        Returns:
            True if unsubscribed successfully
        """
        if subscription_id not in self.subscriptions:
            return False
        
        subscription = self.subscriptions[subscription_id]
        
        # Remove from indices
        if subscription.resource_uri in self.resource_subscriptions:
            self.resource_subscriptions[subscription.resource_uri].remove(subscription_id)
            if not self.resource_subscriptions[subscription.resource_uri]:
                del self.resource_subscriptions[subscription.resource_uri]
        
        if subscription.client_id in self.client_subscriptions:
            self.client_subscriptions[subscription.client_id].remove(subscription_id)
            if not self.client_subscriptions[subscription.client_id]:
                del self.client_subscriptions[subscription.client_id]
        
        # Remove subscription
        del self.subscriptions[subscription_id]
        
        logger.info(f"Unsubscribed: {subscription_id}")
        return True
    
    async def unsubscribe_client(self, client_id: str) -> int:
        """
        Unsubscribe all subscriptions for a client.
        
        Args:
            client_id: Client to unsubscribe
            
        Returns:
            Number of subscriptions removed
        """
        if client_id not in self.client_subscriptions:
            return 0
        
        subscription_ids = self.client_subscriptions[client_id].copy()
        count = 0
        
        for subscription_id in subscription_ids:
            if await self.unsubscribe(subscription_id):
                count += 1
        
        # Remove handler
        if client_id in self.update_handlers:
            del self.update_handlers[client_id]
        
        return count
    
    async def notify_update(
        self,
        resource_uri: str,
        event_type: SubscriptionEvent,
        data: Any,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Notify subscribers of a resource update.
        
        Args:
            resource_uri: URI of updated resource
            event_type: Type of event
            data: Update data
            metadata: Additional metadata
        """
        # Create update event
        update = ResourceUpdate(
            resource_uri=resource_uri,
            event_type=event_type,
            data=data,
            timestamp=datetime.now(),
            metadata=metadata or {}
        )
        
        # Sign update if MACAW available
        if self.server and hasattr(self.server, 'dual_signing'):
            signed = self.server.dual_signing.sign_message(update.to_dict())
            if signed:
                update.signature = signed.signature
        
        # Find matching subscriptions
        matching_subs = self._find_matching_subscriptions(resource_uri, event_type)
        
        # Notify each subscriber
        for subscription_id in matching_subs:
            subscription = self.subscriptions[subscription_id]
            await self._send_update(subscription, update)
    
    def _find_matching_subscriptions(
        self,
        resource_uri: str,
        event_type: SubscriptionEvent
    ) -> List[str]:
        """
        Find subscriptions that match a resource update.
        
        Args:
            resource_uri: URI of updated resource
            event_type: Type of event
            
        Returns:
            List of matching subscription IDs
        """
        matching = []
        
        # Check exact matches
        if resource_uri in self.resource_subscriptions:
            for sub_id in self.resource_subscriptions[resource_uri]:
                subscription = self.subscriptions[sub_id]
                if subscription.matches_event(event_type):
                    matching.append(sub_id)
        
        # Check pattern matches (simplified - real implementation would do glob matching)
        for pattern, sub_ids in self.resource_subscriptions.items():
            if "*" in pattern:
                # Simple wildcard matching
                pattern_base = pattern.replace("*", "")
                if resource_uri.startswith(pattern_base):
                    for sub_id in sub_ids:
                        subscription = self.subscriptions[sub_id]
                        if subscription.matches_event(event_type) and sub_id not in matching:
                            matching.append(sub_id)
        
        return matching
    
    async def _send_update(self, subscription: Subscription, update: ResourceUpdate):
        """
        Send an update to a subscriber.
        
        Args:
            subscription: Subscription to notify
            update: Update to send
        """
        try:
            # Update subscription timestamp
            subscription.last_update = datetime.now()
            
            # Get handler for client
            handler = self.update_handlers.get(subscription.client_id)
            
            if handler:
                # Call handler with update
                await handler(update.to_dict())
                logger.debug(f"Sent update to {subscription.client_id} for {update.resource_uri}")
            else:
                logger.warning(f"No handler for client {subscription.client_id}")
                
        except Exception as e:
            logger.error(f"Failed to send update to {subscription.client_id}: {e}")
    
    def get_subscriptions(self, client_id: Optional[str] = None) -> List[Subscription]:
        """
        Get subscriptions, optionally filtered by client.
        
        Args:
            client_id: Optional client ID to filter by
            
        Returns:
            List of subscriptions
        """
        if client_id:
            sub_ids = self.client_subscriptions.get(client_id, [])
            return [self.subscriptions[sid] for sid in sub_ids]
        else:
            return list(self.subscriptions.values())


class SubscriptionClient:
    """
    Client-side subscription handler for SecureMCP.
    
    Manages subscriptions and handles incoming updates.
    """
    
    def __init__(self, client):
        """
        Initialize subscription client.
        
        Args:
            client: SecureMCP Client instance
        """
        self.client = client
        self.subscriptions: Dict[str, Subscription] = {}
        self.update_callbacks: Dict[str, Callable] = {}  # resource_uri -> callback
        
        logger.info(f"SubscriptionClient initialized for {client.client_id}")
    
    async def subscribe(
        self,
        resource_uri: str,
        callback: Callable,
        event_types: Optional[List[SubscriptionEvent]] = None
    ) -> str:
        """
        Subscribe to resource updates.
        
        Args:
            resource_uri: Resource to subscribe to
            callback: Function to call on updates
            event_types: Types of events to subscribe to
            
        Returns:
            Subscription ID
        """
        # Store callback
        self.update_callbacks[resource_uri] = callback
        
        # Send subscription request to server
        if hasattr(self.client, 'stdio_client'):
            # STDIO transport
            result = await self.client.stdio_client.send_request(
                "resources/subscribe",
                {
                    "uri": resource_uri,
                    "client_id": self.client.client_id,
                    "event_types": [e.value for e in (event_types or [SubscriptionEvent.UPDATED])]
                }
            )
            subscription_id = result.get("subscription_id")
        else:
            # Would implement for other transports
            subscription_id = f"sub-{uuid.uuid4().hex[:8]}"
        
        # Store subscription
        subscription = Subscription(
            subscription_id=subscription_id,
            client_id=self.client.client_id,
            resource_uri=resource_uri,
            created_at=datetime.now(),
            event_types=set(event_types) if event_types else {SubscriptionEvent.UPDATED}
        )
        self.subscriptions[subscription_id] = subscription
        
        logger.info(f"Subscribed to {resource_uri}: {subscription_id}")
        return subscription_id
    
    async def handle_update(self, update_data: Dict[str, Any]):
        """
        Handle an incoming resource update.
        
        Args:
            update_data: Update data from server
        """
        resource_uri = update_data.get("resource_uri")
        
        # Verify signature if present
        if "signature" in update_data and hasattr(self.client, 'dual_signing'):
            # Would verify server signature here
            logger.debug(f"Received signed update for {resource_uri}")
        
        # Find callback
        callback = self.update_callbacks.get(resource_uri)
        
        # Also check pattern matches
        if not callback:
            for pattern, cb in self.update_callbacks.items():
                if "*" in pattern:
                    pattern_base = pattern.replace("*", "")
                    if resource_uri.startswith(pattern_base):
                        callback = cb
                        break
        
        if callback:
            try:
                await callback(update_data)
            except Exception as e:
                logger.error(f"Callback error for {resource_uri}: {e}")
        else:
            logger.warning(f"No callback for resource update: {resource_uri}")
    
    async def unsubscribe(self, subscription_id: str) -> bool:
        """
        Unsubscribe from resource updates.
        
        Args:
            subscription_id: Subscription to cancel
            
        Returns:
            True if unsubscribed successfully
        """
        if subscription_id not in self.subscriptions:
            return False
        
        subscription = self.subscriptions[subscription_id]
        
        # Send unsubscribe request to server
        if hasattr(self.client, 'stdio_client'):
            await self.client.stdio_client.send_request(
                "resources/unsubscribe",
                {"subscription_id": subscription_id}
            )
        
        # Remove callback
        if subscription.resource_uri in self.update_callbacks:
            del self.update_callbacks[subscription.resource_uri]
        
        # Remove subscription
        del self.subscriptions[subscription_id]
        
        logger.info(f"Unsubscribed: {subscription_id}")
        return True