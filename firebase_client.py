"""
Firebase Firestore client with connection pooling and error handling.
Manages all state persistence for the distributed system.
"""
import asyncio
import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import logging

import firebase_admin
from firebase_admin import firestore, credentials
from google.cloud.firestore_v1 import DocumentSnapshot, Query
from google.cloud.firestore_v1.base_query import FieldFilter

from config import CONFIG

logger = logging.getLogger(__name__)

class FirebaseClient:
    """Thread-safe Firebase Firestore client with retry logic"""
    
    def __init__(self):
        self._client = None
        self._initialized = False
        self._batch_size = CONFIG.firestore.batch_size
        self._max_retries = 3
        self._retry_delay = 1.0
        
    def initialize(self) -> None:
        """Initialize Firebase connection with credentials"""
        if self._initialized:
            return
            
        try:
            # Use service account credentials from config
            cred = credentials.Certificate(CONFIG.firebase_creds)
            firebase_admin.initialize_app(cred, {
                'projectId': CONFIG.firestore.project_id,
            })
            self._client = firestore.client()
            self._initialized = True
            logger.info("Firebase Firestore client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Firebase: {e}")
            raise
    
    def _get_collection(self, collection_name: str):
        """Get collection reference with prefix"""
        if not self._initialized:
            self.initialize()
        
        full_name = f"{CONFIG.firestore.collection_prefix}_{collection_name}"
        return self._client.collection(full_name)
    
    async def store_mempool_transaction(
        self, 
        tx_hash: str, 
        chain: str, 
        tx_data: Dict[str, Any]
    ) -> bool:
        """Store mempool transaction with TTL"""
        try:
            collection = self._get_collection("mempool_transactions")
            
            # Add metadata
            tx_data.update({
                "chain": chain,
                "timestamp": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(seconds=30),  # TTL
                "status": "pending"
            })
            
            # Use async thread pool for Firestore operation
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None, 
                lambda: collection.document(tx_hash).set(tx_data)
            )
            
            logger.debug(f"Stored mempool transaction {tx_hash} on {chain}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store mempool transaction {tx_hash}: {e}")
            return False
    
    async def get_pending_transactions(
        self, 
        chain: str, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get pending transactions for a chain"""
        try:
            collection = self._get_collection("mempool_transactions")
            
            # Query for non-expired transactions on specified chain
            loop = asyncio.get_event_loop()
            query = collection.where(
                filter=FieldFilter("chain", "==", chain)
            ).where(
                filter=FieldFilter("expires_at", ">", datetime.utcnow())
            ).limit(limit)
            
            docs = await loop.run_in_executor(None, query.get)
            
            transactions = []
            for doc in docs:
                tx_data = doc.to_dict()
                tx_data["id"] = doc.id
                transactions.append(tx_data)
            
            return transactions
            
        except Exception as e:
            logger.error(f"Failed to get pending transactions for {chain}: {e}")
            return []
    
    async def store_prediction(
        self,
        block_number: int,
        chain: str,
        predictions: Dict[str, Any]
    ) -> bool:
        """Store state predictions for a block"""
        try:
            collection = self._get_collection("predictions")
            doc_id = f"{chain}_{block_number}"
            
            prediction_data = {
                "block_number": block_number,
                "chain": chain,
                "predictions": predictions,
                "timestamp": datetime.utcnow(),
                "processed": False
            }
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: collection.document(doc_id).set(prediction_data)
            )
            
            logger.debug(f"Stored predictions for {chain} block {block_number}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store predictions: {e}")
            return False
    
    async def store_opportunity(
        self,
        opportunity_id: str,
        opportunity_data: Dict[str, Any]
    ) -> bool:
        """Store arbitrage opportunity"""
        try:
            collection = self._get_collection("opportunities")
            
            # Add metadata
            opportunity_data.update({
                "opportunity_id": opportunity_id,
                "created_at": datetime.utcnow(),
                "status": "pending",
                "attempts": 0
            })
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: collection.document(opportunity_id).set(opportunity_data)
            )
            
            logger.info(f"Stored opportunity {opportunity_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to store opportunity {opportunity_id}: {e}")
            return False
    
    async def update_opportunity_status(
        self,
        opportunity_id: str,
        status: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update opportunity status"""
        try:
            collection = self._get_collection("opportunities")
            
            update_data = {
                "status": status,
                "updated_at": datetime.utcnow()
            }
            
            if metadata:
                update_data.update(metadata)
            
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: collection.document(opportunity_id).update(update_data)
            )
            
            logger.debug(f"Updated opportunity {opportunity_id} to {status}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update opportunity {opportunity_id}: {e}")
            return False
    
    async def get_leader(self) -> Optional[str]:
        """Get current leader in distributed orchestration"""
        try:
            collection = self._get_collection("orchestrator")
            
            loop = asyncio.get_event_loop()
            doc = await loop.run_in_executor(
                None,
                lambda: collection.document("leader").get()
            )
            
            if doc.exists:
                data = doc.to_dict()
                # Check if leader heartbeat is recent (within 30 seconds)
                last_heartbeat = data.get("last_heartbeat")
                if isinstance(last_heartbeat, datetime):
                    if datetime.utcnow() - last_heartbeat < timedelta(seconds=30):
                        return data.get("node_id")
            
            return None
            
        except Exception as e:
            logger.error(f"Failed to get leader: {e}")
            return None
    
    async def claim_leadership(
        self,
        node_id: str,
        ttl_seconds: int = 30
    ) -> bool:
        """Attempt to claim leadership"""
        try:
            collection = self._get_collection("orchestrator")
            doc_ref = collection.document("leader")
            
            leadership_data = {
                "node_id": node_id,
                "last_heartbeat": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(seconds=ttl_seconds)
            }
            
            loop = asyncio.get_event_loop()
            
            # Transaction to ensure atomic leader election
            @firestore.transactional
            def claim_transaction(transaction, doc_ref, new_data):
                snapshot = doc_ref.get(transaction=transaction)
                
                if not snapshot.exists:
                    # No current leader, claim it
                    transaction.set(doc_ref, new_data)
                    return True
                
                current_data = snapshot.to_dict()
                current_expiry = current_data.get("expires_at")
                
                if (isinstance(current_expiry, datetime) and 
                    datetime.utcnow() > current_expiry):
                    # Leadership expired, claim it
                    transaction.set(doc_ref, new_data)
                    return True
                
                return False  # Leadership already held by active node
            
            transaction = self._client.transaction()
            success = await loop.run_in_executor(
                None,
                lambda: claim_transaction(transaction, doc_ref, leadership_data)
            )
            
            if success:
                logger.info(f"Node {node_id} claimed leadership")
            else:
                logger.debug(f"Node {node_id} failed to claim leadership")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to claim leadership: {e}")
            return False

# Global Firebase client instance
firebase_client = FirebaseClient()