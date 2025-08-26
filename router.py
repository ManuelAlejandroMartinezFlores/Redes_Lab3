import json
import time
import redis
import threading
from collections import defaultdict
from dijkstra import dijkstra, dijkstra_all
from flooding import flooding_paths

class RouterNode:
    def __init__(self, node_id, neighbors, redis_config, 
                 router_config={'algorithm':'distance_vector', 'routhing_algorithm':None}, 
                 all_nodes=None):
        """
        Initialize a router node with choice of routing algorithm.
        
        Args:
            node_id (str): Unique identifier for this node
            neighbors (list): List of neighbor node IDs
            redis_config (dict): Redis connection configuration
            algorithm (str): 'distance_vector' or 'link_state'
            all_nodes (dict, optional): Information about all nodes
        """
        self.node_id = node_id
        self.neighbors = neighbors
        self.redis_config = redis_config
        self.algorithm = router_config['algorithm']
        self.all_nodes = all_nodes or {}
        
        # Redis connection
        self.r = redis.Redis(
            host=redis_config['host'],
            port=redis_config['port'],
            password=redis_config.get('password'),
            decode_responses=True
        )
        self.pubsub = self.r.pubsub()
        self.routing_algo = router_config['routing_algorithm']
        # Algorithm-specific initialization
        if router_config['algorithm'] == 'distance_vector':
            self._init_distance_vector()
        elif router_config['algorithm'] == 'link_state':
            self._init_link_state()
        else:
            raise ValueError(f"Unknown algorithm: {algorithm}. Choose 'distance_vector' or 'link_state'")
        
        # Common state
        self.running = True
        
        # Subscribe to own channel
        self.pubsub.subscribe(self.node_id)
        
        # Start listening for messages
        threading.Thread(target=self.listen_for_messages, daemon=True).start()
        
        print(f"{self.node_id}: {self.algorithm.upper()} Router initialized")
        print(f"{self.node_id}: Neighbors: {neighbors}")
    
    def set_routing_algorithm(self, algorithm):
        self.routing_algo = algorithm
    
    def _init_distance_vector(self):
        """Initialize Distance Vector specific state."""
        self.distance_vector = {self.node_id: 0}  # Distance to self is 0
        self.routing_table = {}  # Next hop for each destination
        self.neighbor_vectors = {}  # Distance vectors received from neighbors
        
        # Initialize with direct neighbors (cost 1)
        for neighbor in self.neighbors:
            self.distance_vector[neighbor] = 1
            self.routing_table[neighbor] = neighbor
        
        # Send initial distance vector
        self.broadcast_distance_vector()
    
    def _init_link_state(self):
        """Initialize Link State specific state."""
        self.link_state_db = {self.node_id: {'seq_num': 0, 'neighbors': self.neighbors}}
        for n in self.neighbors:
            self.link_state_db[n] = {'seq_num': 0, 'neighbors': [self.node_id]}
        self.seq_num = 0
        self.routing_table = {}
        
        # Flood initial LSA
        self.flood_lsa()
        # Calculate initial routing table
        self.calculate_routing_table()

    def get_known_nodes(self):
        """Get all nodes known to this router."""
        known_nodes = set()
        
        if self.algorithm == 'distance_vector':
            known_nodes = set(self.distance_vector.keys())
        elif self.algorithm == 'link_state':
            known_nodes = set(self.link_state_db.keys())
        
        # Always include ourselves and our direct neighbors
        known_nodes.add(self.node_id)
        known_nodes.update(self.neighbors)
        
        return known_nodes
    
    def send_message(self, destination_id, message):
        """Send a message to another node via Redis with better error handling."""
        try:
            # Add standard message fields
            # message['from'] = self.node_id
            message['to'] = destination_id
            message['hops'] = message.get('hops', 0) + 1
            message['timestamp'] = time.time()
            
            # Check if destination is in our known nodes (optional but helpful)
            if destination_id not in self.get_known_nodes():
                print(f"{self.node_id}: Warning: Destination {destination_id} not in known nodes")
            
            # Publish to destination channel
            self.r.publish(destination_id, json.dumps(message))
            print(f"{self.node_id}: Message sent to {destination_id}")
            
        except redis.ConnectionError as e:
            print(f"{self.node_id}: Redis connection error sending to {destination_id}: {str(e)}")
        except Exception as e:
            print(f"{self.node_id}: Error sending to {destination_id}: {str(e)}")
    
    def broadcast_to_neighbors(self, message, exclude=None):
        """Send a message to all neighbors except excluded ones."""
        exclude = exclude or []
        for neighbor in self.neighbors:
            if neighbor not in exclude:
                self.send_message(neighbor, message)
    
    # ===== DISTANCE VECTOR METHODS =====
    def broadcast_distance_vector(self):
        """Broadcast our distance vector to all neighbors."""
        dv_message = {
            'type': 'DV_UPDATE',
            'distance_vector': self.distance_vector,
            'headers': [{'timestamp': time.time()}],
            'from': self.node_id
        }
        
        print(f"{self.node_id}: Broadcasting DV: {self.distance_vector}")
        self.broadcast_to_neighbors(dv_message)
    
    def process_dv_update(self, dv_msg):
        """Process incoming Distance Vector update."""
        if self.algorithm != 'distance_vector':
            return
            
        source = dv_msg['from']
        received_vector = dv_msg['distance_vector']
        
        print(f"{self.node_id}: Received DV from {source}: {received_vector}")
        
        # Store the neighbor's distance vector
        self.neighbor_vectors[source] = received_vector
        
        # Apply Bellman-Ford algorithm
        updated = self.apply_bellman_ford()
        
        # If our distance vector changed, broadcast the update
        if updated:
            print(f"{self.node_id}: DV updated: {self.distance_vector}")
            print(f"{self.node_id}: Routing table: {self.routing_table}")
            self.broadcast_distance_vector()
    
    def apply_bellman_ford(self):
        """Apply Bellman-Ford algorithm to update distance vector."""
        updated = False
        
        # Check routes through each neighbor
        for neighbor in self.neighbors:
            if neighbor not in self.neighbor_vectors:
                continue
                
            neighbor_vector = self.neighbor_vectors[neighbor]
            cost_to_neighbor = 1  # Assume cost 1 to direct neighbors
            
            # For each destination in neighbor's vector
            for destination, neighbor_cost in neighbor_vector.items():
                if destination == self.node_id:
                    continue
                
                # Calculate total cost through this neighbor
                total_cost = cost_to_neighbor + neighbor_cost
                
                # Update if we found a better path
                if (destination not in self.distance_vector or 
                    total_cost < self.distance_vector[destination]):
                    
                    old_cost = self.distance_vector.get(destination, float('inf'))
                    self.distance_vector[destination] = total_cost
                    self.routing_table[destination] = neighbor
                    
                    print(f"{self.node_id}: Better path to {destination}: {old_cost} -> {total_cost} via {neighbor}")
                    updated = True
        
        return updated
    
    # ===== LINK STATE METHODS =====
    def flood_lsa(self):
        """Flood Link State Advertisement to all neighbors."""
        if self.algorithm != 'link_state':
            return
            
        self.seq_num += 1
        self.link_state_db[self.node_id] = {
            'seq_num': self.seq_num,
            'neighbors': self.neighbors
        }
        
        lsa_message = {
            'type': 'LSA',
            'seq_num': self.seq_num,
            'neighbors': self.neighbors,
            'headers': [{'timestamp': time.time()}],
            'from': self.node_id
        }
        
        print(f"{self.node_id}: Flooding LSA (seq {self.seq_num}) to neighbors: {self.neighbors}")
        self.broadcast_to_neighbors(lsa_message)
    
    def process_lsa(self, lsa):
        """Process incoming Link State Advertisement and learn about other nodes."""
        if self.algorithm != 'link_state':
            return
            
        source = lsa['from']
        seq_num = lsa['seq_num']
        incoming_neighbors = lsa['neighbors']
        
        print(f"{self.node_id}: Processing LSA from {source} (seq {seq_num}) with neighbors: {incoming_neighbors}")
        
        # Check if this is a newer LSA for the source node
        is_new_source_info = (source not in self.link_state_db or 
                            seq_num > self.link_state_db[source].get('seq_num', -1))
        
        # Track if we learned anything new
        learned_something_new = is_new_source_info
        
        # Update our link state database for the source node
        if is_new_source_info:
            self.link_state_db[source] = {
                'seq_num': seq_num,
                'neighbors': incoming_neighbors
            }
            print(f"{self.node_id}: Updated topology with information from {source}")
        
        # Learn about the neighbors mentioned in this LSA
        for neighbor in incoming_neighbors:
            if neighbor != self.node_id:  # Don't create self-reference
                if neighbor not in self.link_state_db:
                    # We discovered a new node!
                    print(f"{self.node_id}: Discovered new node {neighbor} from {source}'s LSA")
                    # Create a basic entry (we don't know its neighbors yet)
                    self.link_state_db[neighbor] = {
                        'seq_num': -1,  # Unknown sequence number
                        'neighbors': [source]  # Unknown neighbors
                    }
                    learned_something_new = True
                elif neighbor == source:
                    print(f"{self.node_id}: Warning: {source} lists itself as a neighbor")
        
        # If we learned something new, recalculate routing and forward
        if learned_something_new:
            print(f"{self.node_id}: Learned new topology information, recalculating routes...")
            self.calculate_routing_table()
            
            # Forward to all neighbors except the source
            self.broadcast_to_neighbors(lsa, exclude=[source])
            print(f"{self.node_id}: Forwarded LSA from {source} to other neighbors")
        else:
            print(f"{self.node_id}: No new information in LSA from {source}")
        
    def build_network_graph(self):
        """Build the complete network graph from link state database."""
        graph = {}
        for node, info in self.link_state_db.items():
            # Convert neighbor list to dict with unit cost (1) for all links
            graph[node] = {neighbor: 1 for neighbor in info['neighbors']}
        return graph
    
    def calculate_routing_table(self):
        """
        Calculate routing table using the specified path algorithm.
        
        Args:
            path_algorithm (str): 'dijkstra' or 'flooding' for path calculation
        """
        if self.algorithm != 'link_state':
            return
            
        graph = self.build_network_graph()
        
        if self.routing_algo == 'dijkstra':
            # Use Dijkstra to calculate shortest paths
            distances, predecessors = dijkstra_all(graph, self.node_id)
            
            # Build routing table: for each destination, the next hop
            self.routing_table = {}
            for destination in graph.keys():
                if destination == self.node_id:
                    continue
                    
                if destination in distances and distances[destination] < float('inf'):
                    # Find the first hop along the shortest path
                    next_hop = destination
                    while predecessors.get(next_hop) != self.node_id:
                        next_hop = predecessors.get(next_hop)
                        if next_hop is None:
                            break
                    
                    if next_hop:
                        self.routing_table[destination] = {
                            'next_hop': next_hop,
                            'cost': distances[destination],
                            'algorithm': 'dijkstra'
                        }
        
        elif self.routing_algo == 'flooding':
            # Use flooding to discover paths to all destinations
            self.routing_table = {}
            
            for destination in graph.keys():
                if destination == self.node_id:
                    continue
                    
                # Use flooding to find paths to this destination
                paths, packets_used = flooding_paths(graph, self.node_id, destination)
                
                if paths:
                    # Select the shortest path found by flooding
                    shortest_path = min(paths, key=len)
                    next_hop = shortest_path[1] if len(shortest_path) > 1 else destination
                    
                    self.routing_table[destination] = {
                        'next_hop': next_hop,
                        'cost': len(shortest_path) - 1,  # Cost is number of hops
                        'paths_found': len(paths),
                        'packets_used': packets_used,
                        'algorithm': 'flooding'
                    }
        
        else:
            raise ValueError(f"Unknown path algorithm: {self.routing_algo}. Choose 'dijkstra' or 'flooding'")
        
        # print(f"{self.node_id}: Routing table updated using {self.routing_algo}: {self.routing_table}")
    
    # ===== COMMON METHODS =====
    def get_next_hop(self, destination):
        """Get next hop for destination based on routing table."""
        if self.algorithm == 'distance_vector':
            return self.routing_table.get(destination)
        elif self.algorithm == 'link_state':
            self.calculate_routing_table()
            route_info = self.routing_table.get(destination)
            return route_info['next_hop'] if route_info else None
    
    def send_data(self, destination_id, message_content):
        """Send data message to another node."""
        next_hop = self.get_next_hop(destination_id)
        
        if not next_hop:
            print(f"{self.node_id}: No route to {destination_id}")
            return False
        
        data_message = {
            'type': 'MESSAGE',
            'payload': message_content,
            'headers': [{'timestamp': time.time()}]
        }
        
        print(f"{self.node_id}: Sending message to {destination_id} via {next_hop}")
        self.send_message(next_hop, data_message)
        return True
    
    def process_message(self, message):
        """Process incoming message based on its type."""
        msg_type = message.get('type', '')
        
        if msg_type == 'DV_UPDATE':
            self.process_dv_update(message)
        elif msg_type == 'LSA':
            self.process_lsa(message)
        elif msg_type == 'MESSAGE':
            self.process_data_message(message)
        elif msg_type == 'HELLO':
            self.process_hello(message)
        else:
            print(f"{self.node_id}: Unknown message type: {msg_type}")
    
    def process_data_message(self, data_msg):
        """Process DATA/MESSAGE."""
        if data_msg.get('to') == self.node_id:
            # Message is for us
            print(f"{self.node_id}: Received MESSAGE from {data_msg['from']}: {data_msg['payload']}")
        else:
            # Message needs to be forwarded
            destination = data_msg['to']
            next_hop = self.get_next_hop(destination)
            
            if next_hop:
                print(f"{self.node_id}: Forwarding message to {destination} via {next_hop}")
                self.send_message(next_hop, data_msg)
            else:
                print(f"{self.node_id}: No route to {destination}, cannot forward message")
    
    def process_hello(self, hello_msg):
        """Process HELLO/PING message."""
        print(f"{self.node_id}: Received HELLO from {hello_msg['from']}")
    
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
                time.sleep(2)
            except json.JSONDecodeError:
                print(f"{self.node_id}: Error decoding message")
            except Exception as e:
                if self.running:
                    print(f"{self.node_id}: Error in message processing - {str(e)}")
    
    def print_routing_info(self):
        """Print the current routing information."""
        print(f"\n{self.node_id} {self.algorithm.upper()} Routing Information:")
        
        if self.algorithm == 'distance_vector':
            print(f"Distance Vector: {self.distance_vector}")
            print("Routing Table:")
            for destination, next_hop in self.routing_table.items():
                cost = self.distance_vector.get(destination, '∞')
                print(f"  {destination} -> via {next_hop} (cost: {cost})")
                
        elif self.algorithm == 'link_state':
            print("Link State Database:")
            for node, info in self.link_state_db.items():
                print(f"  {node}: seq {info['seq_num']}, neighbors: {info['neighbors']}")
            print("Routing Table:")
            self.calculate_routing_table()
            for destination, info in self.routing_table.items():
                print(f"  {destination} -> via {info['next_hop']} (cost: {info['cost']})")
    
    def request_route(self, target):
        """Request information about route to target."""
        if self.algorithm == 'distance_vector':
            if target in self.distance_vector:
                cost = self.distance_vector[target]
                next_hop = self.routing_table.get(target, 'Direct')
                print(f"{self.node_id}: Route to {target}: cost {cost}, via {next_hop}")
                return next_hop, cost
            else:
                print(f"{self.node_id}: No route to {target}")
                return None, float('inf')
                
        elif self.algorithm == 'link_state':
            # self.calculate_routing_table()
            if target in self.routing_table:
                info = self.routing_table[target]
                print(f"{self.node_id}: Route to {target}: cost {info['cost']}, via {info['next_hop']}")
                return info['next_hop'], info['cost']
            else:
                print(f"{self.node_id}: No route to {target}")
                return None, float('inf')
    
    def stop(self):
        """Stop the router."""
        self.running = False
        self.pubsub.close()

# Example usage
if __name__ == "__main__":
    # Redis configuration
    REDIS_CONFIG = {
        'host': 'localhost',
        'port': 6379,
        'password': None
    }
    
    # Get user input for configuration
    print("=== Router Node Configuration ===")
    node_id = input("Node ID: ").strip()
    neighbors_input = input("Neighbors (comma-separated): ").strip()
    neighbors = [n.strip() for n in neighbors_input.split(',')] if neighbors_input else []
    
    algorithm = input("Algorithm (distance_vector/link_state): ").strip().lower()
    if algorithm not in ['distance_vector', 'link_state']:
        algorithm = 'distance_vector'  # Default
    
    # Create router node
    router = RouterNode(node_id, neighbors, REDIS_CONFIG, algorithm)
    
    print(f"\n=== {algorithm.upper()} Router {node_id} Started ===")
    print("Commands:")
    print("  'info' - Show routing information")
    print("  'send <target> <message>' - Send message")
    print("  'route <target>' - Show route to target")
    if algorithm == 'link_state':
        print("  'flood' - Flood LSA to neighbors")
    print("  'quit' - Exit")
    
    try:
        while True:
            command = input("\nCommand: ").strip()
            
            if command == 'info':
                router.print_routing_info()
                
            elif command.startswith('send '):
                parts = command.split(' ', 2)
                if len(parts) >= 3:
                    target = parts[1]
                    message = parts[2]
                    router.send_data(target, message)
                else:
                    print("Usage: send <target> <message>")
                    
            elif command.startswith('route '):
                parts = command.split()
                if len(parts) >= 2:
                    target = parts[1]
                    router.request_route(target)
                else:
                    print("Usage: route <target>")
                    
            elif command == 'flood' and algorithm == 'link_state':
                router.flood_lsa()
                
            elif command == 'quit':
                break
                
            else:
                print("Unknown command")
                
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        router.stop()