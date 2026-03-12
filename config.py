"""
Central configuration management for Project Siphon.
Environment variables are loaded with validation and type conversion.
"""
import os
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import logging

class Chain(Enum):
    POLYGON = "polygon"
    BASE = "base"

@dataclass
class RPCEndpoint:
    """RPC endpoint configuration with failover support"""
    primary: str
    secondary: str
    websocket: Optional[str] = None
    timeout: int = 10

@dataclass
class FirestoreConfig:
    """Firebase Firestore configuration"""
    project_id: str
    collection_prefix: str = "siphon"
    batch_size: int = 500
    timeout: int = 30

@dataclass
class RiskParameters:
    """Dynamic risk management parameters"""
    min_profit_threshold_usd: float = 0.15
    max_gas_percentage: float = 0.3
    max_slippage_bps: int = 50
    consecutive_loss_limit: int = 3
    risk_score_threshold: float = 0.3

class Config:
    """Singleton configuration manager"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Load and validate configuration"""
        # RPC endpoints with fallback
        self.polygon_rpc = RPCEndpoint(
            primary=os.getenv("POLYGON_RPC_PRIMARY", "https://polygon-rpc.com"),
            secondary=os.getenv("POLYGON_RPC_SECONDARY", "https://polygon-mainnet.g.alchemy.com/v2/demo"),
            websocket=os.getenv("POLYGON_WS", "wss://polygon-mainnet.g.alchemy.com/v2/demo")
        )
        
        self.base_rpc = RPCEndpoint(
            primary=os.getenv("BASE_RPC_PRIMARY", "https://mainnet.base.org"),
            secondary=os.getenv("BASE_RPC_SECONDARY", "https://base-mainnet.g.alchemy.com/v2/demo"),
            websocket=os.getenv("BASE_WS", "wss://base-mainnet.g.alchemy.com/v2/demo")
        )
        
        # Firebase configuration
        firebase_creds_json = os.getenv("FIREBASE_CREDENTIALS")
        if not firebase_creds_json:
            raise ValueError("FIREBASE_CREDENTIALS environment variable required")
        
        try:
            firebase_creds = json.loads(firebase_creds_json)
            self.firestore = FirestoreConfig(
                project_id=firebase_creds.get("project_id")
            )
            self.firebase_creds = firebase_creds
        except json.JSONDecodeError as e:
            logging.error(f"Invalid Firebase credentials JSON: {e}")
            raise
        
        # Risk parameters
        self.risk = RiskParameters()
        
        # Execution wallet
        self.execution_wallet_private_key = os.getenv("EXECUTION_WALLET_PRIVATE_KEY")
        if not self.execution_wallet_private_key:
            logging.warning("No execution wallet private key set - simulation mode only")
        
        # Target A wallet (Mac Studio fund)
        self.target_a_wallet = os.getenv("TARGET_A_WALLET", "")
        
        # Service ports for distributed deployment
        self.mempool_service_port = int(os.getenv("MEMPOOL_PORT", "8080"))
        self.simulation_service_port = int(os.getenv("SIMULATION_PORT", "8081"))
        self.validation_service_port = int(os.getenv("VALIDATION_PORT", "8082"))
        
        # Tenderly API for simulation
        self.tenderly_access_key = os.getenv("TENDERLY_ACCESS_KEY", "")
        self.tenderly_user = os.getenv("TENDERLY_USER", "")
        self.tenderly_project = os.getenv("TENDERLY_PROJECT", "")
        
        # Logging configuration
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
        logging.basicConfig(
            level=getattr(logging, self.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

# Global configuration instance
CONFIG = Config()