import json
import time
import redis
import threading
from dijkstra import *
from flooding import *
from collections import defaultdict

class RouterNode:
    def __init__(self, node_id, neighbors, redis_config, all_nodes=None):
        """
        Initialize a router node that can communicate via Redis Pub/Sub.
        
        Args:
            node_id (str): Unique identifier for this node (e.g., "sec10.grupo0.nnovella")
            neighbors (list): List of neighbor node IDs
            redis_config (dict): Configuration for Redis connection
            all_nodes (dict, optional): Information about all nodes in the network
        """
        self.node_id = node_id
        self.neighbors = neighbors
        self.redis_config = redis_config
        self.all_nodes = all_nodes or {}
        
        # Redis connection
        self.r = redis.Redis(
            host=redis_config['host'],
            port=redis_config['port'],
            password=redis_config['password'],
            decode_responses=True
        )
        self.pubsub = self.r.pubsub()
        
        # Algorithm state
        self.link_state_db = {}
        self.seq_num = 0
        self.routing_table = {}
        self.running = True
        
        # Initialize with own link state
        self.update_link_state()
        
        # Subscribe to own channel
        self.pubsub.subscribe(self.node_id)
        
        # Start listening for messages
        threading.Thread(target=self.listen_for_messages, daemon=True).start()
    
    def update_link_state(self):
        """Update the link state database with current neighbor information."""
        self.link_state_db[self.node_id] = {
            'seq_num': self.seq_num,
            'neighbors': list(self.neighbors)
        }
    
    def send_message(self, destination_id, message):
        """Send a message to another node via Redis."""
        try:
            # Add standard message fields
            # message['from'] = self.node_id
            message['to'] = destination_id
            message['hops'] = message.get('hops', 0) + 1
            
            # Publish to destination channel
            self.r.publish(destination_id, json.dumps(message))
            
        except Exception as e:
            print(f"{self.node_id}: Error sending to {destination_id}: {str(e)}")
    
    def broadcast_to_neighbors(self, message, exclude=None):
        """Send a message to all neighbors except excluded ones."""
        exclude = exclude or []
        for neighbor in self.neighbors:
            if neighbor not in exclude:
                self.send_message(neighbor, message)
    
    def flood_lsa(self):
        """Flood Link State Advertisement to all neighbors."""
        self.seq_num += 1
        self.update_link_state()
        
        lsa_message = {
            'type': 'LSA',
            'seq_num': self.seq_num,
            'neighbors': list(self.neighbors),
            'headers': [{'timestamp': time.time()}],
            'from': self.node_id,
        }
        
        print(f"{self.node_id}: Flooding LSA (seq {self.seq_num}) to neighbors: {self.neighbors}")
        self.broadcast_to_neighbors(lsa_message)
    
    def send_hello(self, destination_id):
        """Send a HELLO/PING message to a node."""
        hello_message = {
            'type': 'HELLO',
            'payload': 'Ping request',
            'headers': [{'timestamp': time.time()}]
        }
        self.send_message(destination_id, hello_message)
    
    def send_data(self, destination_id, message_content):
        """Send a DATA/MESSAGE to another node."""
        data_message = {
            'type': 'MESSAGE',
            'payload': message_content,
            'headers': [{'timestamp': time.time()}]
        }
        self.send_message(destination_id, data_message)
    
    def process_message(self, message):
        """Process incoming message based on its type."""
        msg_type = message.get('type', '')
        
        if msg_type == 'LSA':
            self.process_lsa(message)
        elif msg_type == 'HELLO':
            self.process_hello(message)
        elif msg_type == 'MESSAGE':
            self.process_data_message(message)
        elif msg_type == 'TABLE':
            self.process_table_info(message)
        else:
            print(f"{self.node_id}: Unknown message type: {msg_type}")
    
    def process_lsa(self, lsa):
        """Process incoming Link State Advertisement and update topology."""
        source = lsa['from']
        seq_num = lsa['seq_num']
        incoming_neighbors = lsa['neighbors']
        
        # Check if this is a newer LSA or if we have no record of this node
        if (source not in self.link_state_db or 
            seq_num > self.link_state_db[source].get('seq_num', -1)):
            
            # Update our link state database with the new information
            self.link_state_db[source] = {
                'seq_num': seq_num,
                'neighbors': incoming_neighbors
            }
            
            print(f"{self.node_id}: Updated topology with information from {source}")
            print(f"{self.node_id}: {source} neighbors: {incoming_neighbors}")
            
            # Forward to all neighbors except the one it came from
            # This is the key part of the flooding algorithm
            for neighbor in self.neighbors:
                if neighbor != source:  # Don't send back to the source
                    print(f"{self.node_id}: Forwarding LSA from {source} to {neighbor}")
                    self.send_message(neighbor, lsa)
        else:
            # We already have this or a newer LSA, no need to process or forward
            print(f"{self.node_id:}: Ignoring old LSA from {source} (seq {seq_num}, have seq {self.link_state_db[source].get('seq_num', -1)})")
    
    def process_hello(self, hello_msg):
        """Process HELLO/PING message."""
        print(f"{self.node_id}: Received HELLO from {hello_msg['from']}")
        # Could send a response here if needed
    
    def process_data_message(self, data_msg):
        """Process DATA/MESSAGE."""
        print(f"{self.node_id}: Received MESSAGE from {data_msg['from']}: {data_msg['payload']}")
        # If this node is not the final destination, forward according to routing table
        if data_msg.get('to') != self.node_id:
            next_hop = self.get_next_hop(data_msg['to'])
            if next_hop:
                self.send_message(next_hop, data_msg)
    
    def process_table_info(self, table_msg):
        """Process TABLE/INFO message."""
        # Implementation depends on the routing algorithm
        pass
    
    def get_next_hop(self, destination):
        """Get next hop for destination based on routing table."""
        # This would use the calculated routing table
        # Simplified implementation for demonstration
        if destination in self.neighbors:
            return destination
        
        # For more complex routing, use the calculated path
        path, _, _ = self.calculate_path(destination, 'dijkstra')
        if path and len(path) > 1:
            return path[1]  # Next hop is the second element in path
        
        return None
    
    def listen_for_messages(self):
        """Listen for incoming messages from Redis and process them."""
        while self.running:
            try:
                message = self.pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
                if message is not None:
                    decoded_msg = json.loads(message['data'])
                    self.process_message(decoded_msg)
                
            except redis.ConnectionError:
                print(f"{self.node_id}: Redis connection error")
                time.sleep(2)  # Wait before retrying
            except json.JSONDecodeError:
                print(f"{self.node_id}: Error decoding message")
            except Exception as e:
                if self.running:
                    print(f"{self.node_id}: Error in message processing - {str(e)}")
    
    def build_network_graph(self):
        """Build the complete network graph from link state database."""
        graph = {}
        for node, info in self.link_state_db.items():
            # Convert neighbor list to dict with unit cost (1) for all links
            graph[node] = {neighbor: 1 for neighbor in info['neighbors']}
        return graph
    
    def calculate_path(self, target, algorithm='dijkstra'):
        """Calculate path to target using specified algorithm."""
        graph = self.build_network_graph()
        
        if algorithm == 'dijkstra':
            path, cost = dijkstra(graph, self.node_id, target)
            return path, cost, 'dijkstra'
        elif algorithm == 'flooding':
            paths, packets = flooding_paths(graph, self.node_id, target)
            if paths:
                # Return the shortest path found
                shortest_path = min(paths, key=len)
                return shortest_path, packets, 'flooding'
            return [], packets, 'flooding'
        else:
            raise ValueError("Invalid algorithm. Choose 'dijkstra' or 'flooding'.")
    
    def request_route(self, target, algorithm='dijkstra'):
        """Request a route to target using the specified algorithm."""
        path, metric, algo = self.calculate_path(target, algorithm)
        print(f"\n{self.node_id} calculated path to {target} using {algo}:")
        if path:
            print(f"Path: {' → '.join(path)}")
            print(f"{'Cost' if algo == 'dijkstra' else 'Packets'}: {metric}")
        else:
            print(f"No path found to {target}")
        return path
    
    def print_topology(self):
        """Print the current topology known by this router."""
        graph = self.build_network_graph()
        print(f"\nTopología conocida de {self.node_id}, ({len(graph)} nodos):")
        for node, neighbors in graph.items():
            print(f"  {node}: {list(neighbors.keys())}")
    
    def stop(self):
        """Stop the router."""
        self.running = False
        self.pubsub.close()

# Example usage
if __name__ == "__main__":
    # Redis configuration from the lab document
    redis_config = {
        'host': 'lab3.redesuvg.cloud',
        'port': 6379,
        'password': 'UVGRedis2025'
    }
    
    # Example node configuration (would come from the provided files)
    node_id = "sec10.grupo0.nnovella"  # Example format from document
    neighbors = ["sec10.grupo1.user2", "sec10.grupo2.user3"]  # Example neighbors
    
    # Create router node
    router = RouterNode(node_id, neighbors, redis_config)
    
    try:
        # Send initial LSA to announce presence
        router.flood_lsa()
        
        # Wait a bit for topology to stabilize
        time.sleep(2)
        
        # Calculate path to another node
        target = "sec10.grupo3.user4"
        router.request_route(target, 'dijkstra')
        
        # Send a test message
        router.send_data(target, "Hello from our redesigned router!")
        
        # Keep running
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("Shutting down router...")
        router.stop()