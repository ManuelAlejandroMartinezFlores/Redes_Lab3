import json
import time
import redis
import threading
from collections import defaultdict
from dijkstra import dijkstra, dijkstra_all
from flooding import flooding_paths

class RouterNode:
    def __init__(self, node_id, neighbors, redis_config, 
                 algorithm):
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
        self.neighbors = {n: 1 for n in neighbors}
        self.redis_config = redis_config
        self.algorithm = algorithm
        self.all_nodes = {}

        self.neighbor_last_seen = {neighbor: time.time() for neighbor in neighbors}
        self.known_neighbors = set(neighbors)  # All neighbors we've ever known
        self.hello_interval = 5  # seconds between hello messages
        self.timeout_threshold = 15  # seconds to consider neighbor dead
        self.discovery_interval = 30  # seconds between discovery attempts
        self.max_hops = 50
        self.lsa_interval = 10
        
        # Redis connection
        self.r = redis.Redis(
            host=redis_config['host'],
            port=redis_config['port'],
            password=redis_config.get('password'),
            decode_responses=True
        )
        self.pubsub = self.r.pubsub()
        # Algorithm-specific initialization
        
        
        # Common state
        self.running = True
        
        # Subscribe to own channel
        self.pubsub.subscribe(self.node_id)
        
        # Start listening for messages
        threading.Thread(target=self.listen_for_messages, daemon=True).start()
        self._send_hello_to_neighbors()
        
        if self.algorithm == 'link_state':
            self._init_link_state()
            threading.Thread(target=self._monitor_neighbors, daemon=True).start()
            threading.Thread(target=self._communicate_lsa, daemon=True).start()
        elif self.algorithm != 'flooding':
            raise ValueError(f"Unknown algorithm: {algorithm}. Choose 'flooding' or 'link_state'")

    def _communicate_lsa(self):
        while self.running:
            try:
                self.flood_lsa()
                time.sleep(self.lsa_interval)
            except Exception as e:
                print(f"{self.node_id}: Error en comunicar LSA: {e}")
    def _monitor_neighbors(self):
        """Monitor neighbors for failure detection."""
        while self.running:
            try:
                current_time = time.time()
                dead_neighbors = []
                
                # Check for timed out neighbors
                for neighbor in list(self.neighbor_last_seen.keys()):
                    if current_time - self.neighbor_last_seen[neighbor] > self.timeout_threshold:
                        if neighbor in self.neighbors.keys():  # Only if still considered active
                            dead_neighbors.append(neighbor)
                            print(f"{self.node_id}: Vecino {neighbor} parece estar caído (timeout)")
                
                # Handle dead neighbors
                for dead_neighbor in dead_neighbors:
                    self._handle_neighbor_failure(dead_neighbor)
                
                # Send hello messages to active neighbors
                self._send_echo_to_neighbors()
                
                time.sleep(self.hello_interval)
                
            except Exception as e:
                print(f"{self.node_id}: Error en monitoreo de vecinos: {e}")
    
    def _send_hello_to_neighbors(self):
        """Send hello messages to all active neighbors."""
        for neighbor in self.neighbors.keys():
            self.send_hello(neighbor)

    def send_echo(self, target):
        msg = {
            'from': self.node_id,
            'to': target,
            'type': 'echo',
            'headers': {'alg': self.algorithm},
            'payload': 'echo'
        }
        self.send_message(target, msg)

    def _send_echo_to_neighbors(self):
        for n in self.neighbors.keys():
            self.send_echo(n)
    
    def _handle_neighbor_failure(self, dead_neighbor):
        """Handle a neighbor failure."""
        print(f"{self.node_id}: Manejando caída del vecino {dead_neighbor}")
        
        # Remove from active neighbors
        if dead_neighbor in self.neighbors.keys():
            del self.neighbors[dead_neighbor]
        
        # Remove from monitoring (but keep in known_neighbors for rediscovery)
        if dead_neighbor in self.neighbor_last_seen:
            del self.neighbor_last_seen[dead_neighbor]
              
        if self.algorithm == 'link_state':
            # Update link state database
            self.link_state_db[self.node_id] = {
                'seq_num': self.seq_num,
                'neighbors': self.neighbors.copy()
            }
            self.seq_num += 1
            # Flood updated LSA
            self.flood_lsa()
            
            # Recalculate routing table
            self.calculate_routing_table()
    
    def _handle_new_neighbor(self, new_neighbor):
        """Handle discovery of a new neighbor."""
        print(f"{self.node_id}: Nuevo vecino descubierto: {new_neighbor}")
        
        # Add to active neighbors
        if new_neighbor not in self.neighbors:
            self.neighbors[new_neighbor]= 1
        
        # Add to monitoring
        self.neighbor_last_seen[new_neighbor] = time.time()
        self.known_neighbors.add(new_neighbor)
            
        if self.algorithm == 'link_state':
            self.seq_num += 1
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
            # message['from'] = self.node_id
            message['to'] = destination_id
            message['hops'] = message.get('hops', 0) + 1
            message['timestamp'] = time.time()
            
            # Publish to destination channel
            self.r.publish(destination_id, json.dumps(message))
            
        except Exception as e:
            print(f"{self.node_id}: Error enviando a {destination_id}: {str(e)}")
    
    
    def send_hello(self, destination_id):
        """Send HELLO message to a node."""
        hello_message = {
            'type': 'hello',
            'payload': 'ping',
            'headers': {'alg': self.algorithm},
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
        if source not in self.neighbors.keys():
            self._handle_new_neighbor(source)
        # else:
        # print(f"{self.node_id}: HELLO de {source}")
    
    def _init_link_state(self):
        """Initialize Link State specific state."""
        self.link_state_db = {self.node_id: {'seq_num': 0, 'neighbors': self.neighbors}}
        for n in self.neighbors.keys():
            self.link_state_db[n] = {'seq_num': 0, 'neighbors': {self.node_id: self.neighbors[n]}}
        self.seq_num = 0
        self.routing_table = {}
        
        # Flood initial LSA
        self.flood_lsa()
        # Calculate initial routing table
        self.calculate_routing_table()

    def get_known_nodes(self):
        """Get all nodes known to this router."""
        known_nodes = set()
    
        if self.algorithm == 'link_state':
            known_nodes = set(self.link_state_db.keys())
        
        # Always include ourselves and our direct neighbors
        known_nodes.add(self.node_id)
        known_nodes.update(self.neighbors.keys())
        
        return known_nodes
    
    def send_message(self, destination_id, message):
        """Send a message to another node via Redis with better error handling."""
        try:
            # Add standard message fields
            # message['from'] = self.node_id
            # message['to'] = destination_id
            message['hops'] = message.get('hops', 0) + 1
            message['timestamp'] = time.time()
            
            # Check if destination is in our known nodes (optional but helpful)
            if destination_id not in self.get_known_nodes():
                print(f"{self.node_id}: Advertencia: Destino {destination_id} no es conocido")
            
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
        for neighbor in self.neighbors.keys():
            if neighbor not in exclude:
                self.send_message(neighbor, message)
    
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
            'type': 'info',
            'seq_num': self.seq_num,
            'neighbors': self.neighbors,
            'headers': {'alg': self.algorithm},
            'from': self.node_id
        }
        
        # print(f"{self.node_id}: Compartiendo LSA (seq {self.seq_num}) a vecinos: {self.neighbors}")
        self.broadcast_to_neighbors(lsa_message)
    
    def process_lsa(self, lsa):
        """Process incoming Link State Advertisement and learn about other nodes."""
        if self.algorithm != 'link_state':
            return
            
        source = lsa['from']
        seq_num = lsa['seq_num']
        incoming_neighbors = lsa['neighbors']
        
        # print(f"{self.node_id}: Procesando LSA de {source} (seq {seq_num}) con vecinos: {incoming_neighbors}")
        
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
            # print(f"{self.node_id}: Topología actualizada con información de {source}")
        
        # Learn about the neighbors mentioned in this LSA
        for neighbor in incoming_neighbors:
            if neighbor != self.node_id:  # Don't create self-reference
                if neighbor not in self.link_state_db:
                    # We discovered a new node!
                    # print(f"{self.node_id}: Nodo {neighbor} descubiernto por LSA de {source}")
                    # Create a basic entry (we don't know its neighbors yet)
                    self.link_state_db[neighbor] = {
                        'seq_num': -1,  # Unknown sequence number
                        'neighbors': {source: 1}  # Unknown neighbors
                    }
                    learned_something_new = True
                elif neighbor == source:
                    print(f"{self.node_id}: Advertencia: {source} es su propio veciono")
        
        # If we learned something new, recalculate routing and forward
        if learned_something_new:
            # print(f"{self.node_id}: Recalculado rutas")
            self.calculate_routing_table()
            
            # Forward to all neighbors except the source
            self.broadcast_to_neighbors(lsa, exclude=[source])
            # print(f"{self.node_id}: Compartiendo LSA de {source} a vecinos")
        # else:
            # print(f"{self.node_id}: No hay nueva información en LSA de {source}")
        
    def build_network_graph(self):
        """Build the complete network graph from link state database."""
        graph = {}
        for node, info in self.link_state_db.items():
            # Convert neighbor list to dict with unit cost (1) for all links
            graph[node] = info['neighbors']
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

    
    # ===== COMMON METHODS =====
    def get_next_hop(self, destination):
        """Get next hop for destination based on routing table."""
        if self.algorithm == 'link_state':
            self.calculate_routing_table()
            route_info = self.routing_table.get(destination)
            return route_info['next_hop'] if route_info else None
    
    def send_data(self, destination_id, message_content):
        """Send data message to another node.""" 
        data_message = {
            'type': 'message',
            'payload': message_content,
            'headers': {'alg': self.algorithm},
            'from': self.node_id,
            'to': destination_id
        }
        if self.algorithm == 'link_state':
            next_hop = self.get_next_hop(destination_id)
            if not next_hop:
                print(f"{self.node_id}: No existe ruta hacia {destination_id}")
                return False
            print(f"{self.node_id}: Enviando mensaje a {destination_id} via {next_hop}")
            self.send_message(next_hop, data_message)
            return True
        else: 
            self.broadcast_to_neighbors(data_message)
            print('Flooding mensajen a vecinos')
            return True
    
    def process_data_message(self, data_msg):
        """Process DATA/MESSAGE."""
        if data_msg.get('to') == self.node_id:
            # Message is for us
            print(f"{self.node_id}: MESSAGE recibido de {data_msg['from']}: {data_msg['payload']}")
        else:
            # Message needs to be forwarded
            if self.algorithm == 'link_state':
                destination = data_msg['to']
                next_hop = self.get_next_hop(destination)
                if next_hop:
                    print(f"{self.node_id}: Compartiendo mensaje a {destination} via {next_hop}")
                    self.send_message(next_hop, data_msg)
                else:
                    print(f"{self.node_id}: No hay ruta a {destination}, no se puede compartir mensaje")
            else:
                if data_msg.get('hops', 0) > self.max_hops:
                    return
                if data_msg.get('to', '') in self.neighbors.keys():
                    self.send_message(data_msg.get('to', ''), data_msg)
                    print(f"Compartiendo mensaje a {data_msg.get('to', '')}")
                    return 
                self.broadcast_to_neighbors(data_msg, exclude=[data_msg['from']])
    
    
    def process_echo(self, message):
        target = message['from']
        if target not in self.neighbors.keys():
            self._handle_new_neighbor(target)
        self.send_hello(target)

    def process_message(self, message):
        """Process incoming message based on its type."""
        msg_type = message.get('type', '')
        
        if msg_type == 'info':
            self.process_lsa(message)
        elif msg_type == 'message':
            self.process_data_message(message)
        elif msg_type == 'hello':
            self.process_hello(message)
        elif msg_type == 'echo':
            self.process_echo(message)
        else:
            print(f"{self.node_id}: tipo desconocido: {msg_type}")
    
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
            print(f"{self.node_id}: Vecino {neighbor_id} agregado para descubrimiento")
            self.send_hello(neighbor_id)
        else:
            print(f"{self.node_id}: Vecino {neighbor_id} ya conocido")
    
    def remove_neighbor(self, neighbor_id):
        """Manually remove a neighbor."""
        if neighbor_id in self.neighbors.keys():
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
        print("Vecinos activos:", self.neighbors.keys())
        print("Vecinos conocidos:", list(self.known_neighbors))
        print("Última vez vistos:")
        for neighbor, last_seen in self.neighbor_last_seen.items():
            status = "ACTIVO" if neighbor in self.neighbors else "INACTIVO"
            age = current_time - last_seen
            print(f"  {neighbor}: {status}, hace {age:.1f}s")

    
    def print_routing_info(self):
        """Print the current routing information."""
        print(f"\n{self.node_id} {self.algorithm.upper()} Información de rutas:")
                
        if self.algorithm == 'link_state':
            print("Link State Database:")
            for node, info in self.link_state_db.items():
                print(f"  {node}: seq {info['seq_num']}, vecinos: {info['neighbors']}")
            print("Routing Table:")
            self.calculate_routing_table()
            for destination, info in self.routing_table.items():
                print(f"  {destination} -> via {info['next_hop']} (costo: {info['cost']})")
        else:
            print('Vecinos')
            print(self.neighbors)
    
    def request_route(self, target):
        """Request information about route to target."""            
        if self.algorithm == 'link_state':
            # self.calculate_routing_table()
            if target in self.routing_table:
                info = self.routing_table[target]
                print(f"{self.node_id}: Ruta hacia {target}: costo {info['cost']}, via {info['next_hop']}")
                return info['next_hop'], info['cost']
            else:
                print(f"{self.node_id}: No existe ruta hacia {target}")
                return None, float('inf')
        return None, float('inf')
    
    def stop(self):
        """Stop the router."""
        self.running = False
        self.pubsub.close()


{
    'type': 'hello|message|info|echo',
    'from': 'sec10.....',
    'to': 'sec10....',
    'hops': 0,
    'headers': {'alg': 'dijkstra|flooding|lsr'},
    'seq_num': 0, # info
    'neighbors': {'sec10...': 1, 'sec10....': 1}, # info
    'payload': 'dafdsa' # message
}