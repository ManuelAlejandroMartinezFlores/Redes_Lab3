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

        self.neighbor_last_seen = {neighbor: time.time() for neighbor in neighbors}
        self.known_neighbors = set(neighbors)  # All neighbors we've ever known
        self.hello_interval = 5  # seconds between hello messages
        self.timeout_threshold = 15  # seconds to consider neighbor dead
        self.discovery_interval = 30  # seconds between discovery attempts
        
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
        
        # Start neighbor monitoring
        threading.Thread(target=self._monitor_neighbors, daemon=True).start()
        
        # Start neighbor discovery
        # threading.Thread(target=self._discover_neighbors, daemon=True).start()

        
    
    
    def _monitor_neighbors(self):
        """Monitor neighbors for failure detection."""
        while self.running:
            try:
                current_time = time.time()
                dead_neighbors = []
                
                # Check for timed out neighbors
                for neighbor in list(self.neighbor_last_seen.keys()):
                    if current_time - self.neighbor_last_seen[neighbor] > self.timeout_threshold:
                        if neighbor in self.neighbors:  # Only if still considered active
                            dead_neighbors.append(neighbor)
                            print(f"{self.node_id}: Vecino {neighbor} parece estar caído (timeout)")
                
                # Handle dead neighbors
                for dead_neighbor in dead_neighbors:
                    self._handle_neighbor_failure(dead_neighbor)
                
                # Send hello messages to active neighbors
                self._send_hello_to_neighbors()
                
                time.sleep(self.hello_interval)
                
            except Exception as e:
                print(f"{self.node_id}: Error en monitoreo de vecinos: {e}")
    
    def _discover_neighbors(self):
        """Periodically attempt to discover new neighbors."""
        while self.running:
            try:
                # Send discovery messages to known but inactive neighbors
                inactive_neighbors = self.known_neighbors# - set(self.neighbors)
                for neighbor in inactive_neighbors:
                    self.send_hello(neighbor)
                    # print(f"{self.node_id}: 🔍 Intentando redescubrir vecino {neighbor}")
                
                time.sleep(self.discovery_interval)
                
            except Exception as e:
                print(f"{self.node_id}: Error en descubrimiento de vecinos: {e}")
    
    def _send_hello_to_neighbors(self):
        """Send hello messages to all active neighbors."""
        for neighbor in self.neighbors:
            self.send_hello(neighbor)
    
    def _handle_neighbor_failure(self, dead_neighbor):
        """Handle a neighbor failure."""
        print(f"{self.node_id}: Manejando caída del vecino {dead_neighbor}")
        
        # Remove from active neighbors
        if dead_neighbor in self.neighbors:
            self.neighbors.remove(dead_neighbor)
        
        # Remove from monitoring (but keep in known_neighbors for rediscovery)
        if dead_neighbor in self.neighbor_last_seen:
            del self.neighbor_last_seen[dead_neighbor]
        
        if self.algorithm == 'distance_vector':
            # Remove from neighbor vectors
            if dead_neighbor in self.neighbor_vectors:
                del self.neighbor_vectors[dead_neighbor]

            routes_to_invalidate = []
            for destination, next_hop in self.routing_table.items():
                if next_hop == dead_neighbor:
                    routes_to_invalidate.append(destination)
            
            # Invalidate these routes by setting cost to infinity
            for destination in routes_to_invalidate:
                self.distance_vector[destination] = float('inf')
                if destination in self.routing_table:
                    del self.routing_table[destination]
                print(f"{self.node_id}: Invalidated route to {destination} (via {dead_neighbor})")
            
            # Remove the neighbor itself from distance vector
            if dead_neighbor in self.distance_vector:
                del self.distance_vector[dead_neighbor]
            
            # Force immediate Bellman-Ford recalculation and broadcast
            self.apply_bellman_ford()
            
            # Always broadcast after a neighbor failure, even if no immediate change
            # This ensures the failure information propagates through the network
            print(f"{self.node_id}: Broadcasting failure update for {dead_neighbor}")
            self.broadcast_distance_vector()
            
            
        elif self.algorithm == 'link_state':
            # Update link state database
            self.link_state_db[self.node_id] = {
                'seq_num': self.seq_num,
                'neighbors': self.neighbors.copy()
            }
            
            # Flood updated LSA
            self.flood_lsa()
            
            # Recalculate routing table
            self.calculate_routing_table()
    
    def _handle_new_neighbor(self, new_neighbor):
        """Handle discovery of a new neighbor."""
        print(f"{self.node_id}: Nuevo vecino descubierto: {new_neighbor}")
        
        # Add to active neighbors
        if new_neighbor not in self.neighbors:
            self.neighbors.append(new_neighbor)
        
        # Add to monitoring
        self.neighbor_last_seen[new_neighbor] = time.time()
        self.known_neighbors.add(new_neighbor)
        
        if self.algorithm == 'distance_vector':
            # Add to distance vector and routing table
            self.distance_vector[new_neighbor] = 1
            self.routing_table[new_neighbor] = new_neighbor
            
            # Request distance vector from new neighbor
            self.send_hello(new_neighbor)
            
            # Recalculate and broadcast
            updated = self.apply_bellman_ford()
            if updated:
                self.broadcast_distance_vector()
            
        elif self.algorithm == 'link_state':
            # Update link state database
            self.link_state_db[self.node_id] = {
                'seq_num': self.seq_num,
                'neighbors': self.neighbors.copy()
            }
            
            # Flood updated LSA
            self.flood_lsa()
            
            # Recalculate routing table
            self.calculate_routing_table()
    
    def send_message(self, destination_id, message):
        """Send a message to another node via Redis."""
        try:
            # Add standard message fields
            message['from'] = self.node_id
            message['to'] = destination_id
            message['hops'] = message.get('hops', 0) + 1
            message['timestamp'] = time.time()
            
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
    
    def send_hello(self, destination_id):
        """Send HELLO message to a node."""
        hello_message = {
            'type': 'HELLO',
            'payload': 'ping',
            'headers': [{'timestamp': time.time()}],
            'from': self.node_id
        }
        self.send_message(destination_id, hello_message)
    
    def process_hello(self, hello_msg):
        """Process HELLO message and update neighbor status."""
        source = hello_msg['from']
        
        # Update last seen time
        self.neighbor_last_seen[source] = time.time()
        self.known_neighbors.add(source)
        
        # If this is a new neighbor, handle it
        if source not in self.neighbors:
            self._handle_new_neighbor(source)
        # else:
        #     print(f"{self.node_id}: Received HELLO from {source}")
    def set_routing_algorithm(self, algorithm):
        self.routing_algo = algorithm
    
    def _init_distance_vector(self):
        """Initialize Distance Vector specific state with poison reverse."""
        self.distance_vector = {self.node_id: 0}  # Distance to self is 0
        self.routing_table = {}  # Next hop for each destination
        self.neighbor_vectors = {}  # Distance vectors received from neighbors
        self.poison_reverse = True  # Enable poison reverse
        self.split_horizon = True  # Enable split horizon
        
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
            # print(f"{self.node_id}: Message sent to {destination_id}")
            
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
        """Broadcast distance vector to all neighbors with poison reverse."""
        for neighbor in self.neighbors:
            neighbor_dv = {}
            
            # Include all routes except those that would cause routing loops
            for destination, cost in self.distance_vector.items():
                next_hop = self.routing_table.get(destination)
                
                # Basic split horizon: don't advertise route back to the neighbor that gave it to us
                if next_hop == neighbor and destination != neighbor:
                    # Poison reverse: advertise infinite cost instead of omitting
                    neighbor_dv[destination] = float('inf')
                else:
                    neighbor_dv[destination] = cost
            
            # Always include direct neighbor routes
            if neighbor in self.distance_vector:
                neighbor_dv[neighbor] = self.distance_vector[neighbor]
            
            dv_message = {
                'type': 'DV_UPDATE',
                'distance_vector': neighbor_dv,
                'headers': [{
                    'timestamp': time.time(),
                    'source': self.node_id
                }],
                'from': self.node_id
            }
        
            print(f"{self.node_id}: Sending DV to {neighbor}: {neighbor_dv}")
            self.send_message(neighbor, dv_message)
    
    def process_dv_update(self, dv_msg):
        """Process incoming Distance Vector update."""
        source = dv_msg['from']
        received_vector = dv_msg['distance_vector']
        
        print(f"{self.node_id}: Received DV from {source}: {received_vector}")
        
        # Store the neighbor's distance vector
        self.neighbor_vectors[source] = received_vector
        
        # Update last seen time for this neighbor
        self.neighbor_last_seen[source] = time.time()
        
        # Apply Bellman-Ford algorithm
        updated = self.apply_bellman_ford()
        
        # If our distance vector changed, broadcast the update
        if updated:
            print(f"{self.node_id}: DV updated: {self.distance_vector}")
            print(f"{self.node_id}: Routing table: {self.routing_table}")
            self.broadcast_distance_vector()
            
    def apply_bellman_ford(self):
        """Apply Bellman-Ford algorithm with change detection."""
        infinity = float('inf')
        
        # Store old state for comparison
        old_distance_vector = self.distance_vector.copy()
        old_routing_table = self.routing_table.copy()
        
        # Create new temporary tables
        new_distance_vector = {self.node_id: 0}
        new_routing_table = {}
        
        # Add direct neighbors
        for neighbor in self.neighbors:
            new_distance_vector[neighbor] = 1
            new_routing_table[neighbor] = neighbor
        
        # Process neighbor vectors
        for neighbor in self.neighbors:
            if neighbor not in self.neighbor_vectors:
                continue
                
            neighbor_vector = self.neighbor_vectors[neighbor]
            cost_to_neighbor = 1
            
            for destination, neighbor_cost in neighbor_vector.items():
                if destination == self.node_id or neighbor_cost == infinity:
                    continue
                    
                total_cost = cost_to_neighbor + neighbor_cost
                current_cost = new_distance_vector.get(destination, infinity)
                
                if total_cost < current_cost:
                    new_distance_vector[destination] = total_cost
                    new_routing_table[destination] = neighbor
        
        # Check if anything actually changed
        changed = False
        
        # Check for new or updated routes
        for destination, new_cost in new_distance_vector.items():
            old_cost = old_distance_vector.get(destination, infinity)
            old_next_hop = old_routing_table.get(destination)
            new_next_hop = new_routing_table.get(destination)
            
            if (new_cost != old_cost or new_next_hop != old_next_hop):
                changed = True
                break
        
        # Check for removed routes
        for destination in old_distance_vector:
            if destination not in new_distance_vector and destination != self.node_id:
                changed = True
                break
        
        # Only update if something changed
        if changed:
            self.distance_vector = new_distance_vector
            self.routing_table = new_routing_table
            print(f"{self.node_id}: DV changed: {self.distance_vector}")
            return True
        
        return False
    
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
    
    # def process_hello(self, hello_msg):
    #     """Process HELLO/PING message."""
    #     print(f"{self.node_id}: Received HELLO from {hello_msg['from']}")
    
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
    
    def add_static_neighbor(self, neighbor_id):
        """Manually add a neighbor for discovery attempts."""
        if neighbor_id not in self.known_neighbors:
            self.known_neighbors.add(neighbor_id)
            print(f"{self.node_id}: 🔍 Vecino {neighbor_id} agregado para descubrimiento")
            self.send_hello(neighbor_id)
        else:
            print(f"{self.node_id}: Vecino {neighbor_id} ya conocido")
    
    def remove_neighbor(self, neighbor_id):
        """Manually remove a neighbor."""
        if neighbor_id in self.neighbors:
            self._handle_neighbor_failure(neighbor_id)
        elif neighbor_id in self.known_neighbors:
            self.known_neighbors.remove(neighbor_id)
            print(f"{self.node_id}: Vecino {neighbor_id} removido")
        else:
            print(f"{self.node_id}: Vecino {neighbor_id} no encontrado")
    
    def print_neighbor_status(self):
        """Print current neighbor status."""
        current_time = time.time()
        print(f"\n{self.node_id} Estado de Vecinos:")
        print("Vecinos activos:", self.neighbors)
        print("Vecinos conocidos:", list(self.known_neighbors))
        print("Última vez vistos:")
        for neighbor, last_seen in self.neighbor_last_seen.items():
            status = "✅ ACTIVO" if neighbor in self.neighbors else "❌ INACTIVO"
            age = current_time - last_seen
            print(f"  {neighbor}: {status}, hace {age:.1f}s")

    
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
