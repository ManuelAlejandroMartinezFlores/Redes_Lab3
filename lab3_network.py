import socket
import threading
import json
import time
from collections import defaultdict

class RouterNode:
    def __init__(self, node_id, neighbors, port, all_nodes):
        """
        Initialize a router node that can communicate via sockets.
        
        Args:
            node_id (str): Unique identifier for this node
            neighbors (dict): {neighbor_id: cost} pairs
            port (int): Base port number for this node
            all_nodes (dict): Information about all nodes in the network
        """
        self.node_id = node_id
        self.neighbors = neighbors
        self.port = port
        self.all_nodes = all_nodes
        self.link_state_db = {}
        self.seq_num = 0
        self.routing_table = {}
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(('localhost', port))
        self.running = True
        
        # Initialize with own link state
        self.update_link_state()
        
        # Start listening for messages
        threading.Thread(target=self.listen_for_messages, daemon=True).start()
    
    def update_link_state(self):
        """Update the link state database with current neighbor information."""
        self.link_state_db[self.node_id] = {
            'seq_num': self.seq_num,
            'neighbors': dict(self.neighbors)
        }
    
    def send_message(self, destination_id, message):
        """Send a message to another node."""
        dest_port = self.all_nodes[destination_id]['port']
        self.socket.sendto(json.dumps(message).encode(), ('localhost', dest_port))
    
    def flood_lsa(self):
        """Flood Link State Advertisement to all neighbors."""
        self.seq_num += 1
        self.update_link_state()
        
        lsa = {
            'type': 'LSA',
            'source': self.node_id,
            'seq_num': self.seq_num,
            'neighbors': dict(self.neighbors)
        }
        
        for neighbor in self.neighbors:
            self.send_message(neighbor, lsa)
    
    def listen_for_messages(self):
        """Listen for incoming messages and process them."""
        while self.running:
            try:
                data, addr = self.socket.recvfrom(1024)
                message = json.loads(data.decode())
                
                if message['type'] == 'LSA':
                    self.process_lsa(message)
                elif message['type'] == 'ROUTE_REQUEST':
                    self.process_route_request(message)
                elif message['type'] == 'ROUTE_RESPONSE':
                    self.process_route_response(message)
                    
            except json.JSONDecodeError:
                print(f"{self.node_id}: Error decoding message")
            except Exception as e:
                print(f"{self.node_id}: Error in message processing - {str(e)}")
    
    def process_lsa(self, lsa):
        """Process incoming Link State Advertisement."""
        source = lsa['source']
        seq_num = lsa['seq_num']
        
        # Update if this is a newer LSA
        if source not in self.link_state_db or seq_num > self.link_state_db[source].get('seq_num', -1):
            self.link_state_db[source] = {
                'seq_num': seq_num,
                'neighbors': lsa['neighbors']
            }
            
            # Forward to all neighbors except the one it came from
            for neighbor in self.neighbors:
                if neighbor != source:
                    self.send_message(neighbor, lsa)
    
    def build_network_graph(self):
        """Build the complete network graph from link state database."""
        graph = {}
        for node, info in self.link_state_db.items():
            graph[node] = info['neighbors']
        return graph
    
    def dijkstra(self, graph, start, target):
        """Dijkstra's algorithm implementation."""
        if start not in graph or target not in graph:
            return [], float('infinity')
        
        distances = {node: float('infinity') for node in graph}
        distances[start] = 0
        previous_nodes = {node: None for node in graph}
        
        priority_queue = [(0, start)]
        
        while priority_queue:
            current_distance, current_node = heapq.heappop(priority_queue)
            
            if current_node == target:
                break
                
            if current_distance > distances[current_node]:
                continue
                
            for neighbor, weight in graph[current_node].items():
                distance = current_distance + weight
                if distance < distances[neighbor]:
                    distances[neighbor] = distance
                    previous_nodes[neighbor] = current_node
                    heapq.heappush(priority_queue, (distance, neighbor))
        
        # Reconstruct path
        path = []
        node = target
        while node is not None:
            path.append(node)
            node = previous_nodes[node]
        path = path[::-1]
        
        return (path, distances[target]) if path and path[0] == start else ([], float('infinity'))
    
    def flooding_paths(self, graph, start, target):
        """Flooding algorithm implementation."""
        if start not in graph or target not in graph:
            return [], 0
        
        visited = defaultdict(set)
        paths = []
        packet_counter = 0
        
        queue = deque()
        queue.append((start, [start], None))
        packet_counter += 1
        
        while queue:
            current_node, path, incoming_node = queue.popleft()
            
            if current_node == target:
                paths.append(path)
                continue
            
            visited[current_node].add(incoming_node)
            
            for neighbor in graph[current_node]:
                if neighbor != incoming_node:
                    new_path = path.copy()
                    new_path.append(neighbor)
                    queue.append((neighbor, new_path, current_node))
                    packet_counter += 1
        
        return paths, packet_counter
    
    def calculate_path(self, target, algorithm='dijkstra'):
        """Calculate path to target using specified algorithm."""
        graph = self.build_network_graph()
        
        if algorithm == 'dijkstra':
            path, cost = self.dijkstra(graph, self.node_id, target)
            return path, cost, 'dijkstra'
        elif algorithm == 'flooding':
            paths, packets = self.flooding_paths(graph, self.node_id, target)
            return (paths[0] if paths else []), packets, 'flooding'
        else:
            raise ValueError("Invalid algorithm. Choose 'dijkstra' or 'flooding'.")
    
    def request_route(self, target, algorithm='dijkstra'):
        """Request a route to target using the specified algorithm."""
        path, metric, algo = self.calculate_path(target, algorithm)
        print(f"\n{self.node_id} calculated path to {target} using {algo}:")
        print(f"Path: {' → '.join(path)}")
        print(f"{'Cost' if algo == 'dijkstra' else 'Packets'}: {metric}")
        return path
    
    def stop(self):
        """Stop the router."""
        self.running = False
        self.socket.close()

def create_network():
    """Create a test network with multiple router nodes."""
    # Define network topology and ports
    network = {
        'A': {'neighbors': {'B': 1, 'C': 4}, 'port': 5000},
        'B': {'neighbors': {'A': 1, 'C': 2, 'D': 5}, 'port': 5001},
        'C': {'neighbors': {'A': 4, 'B': 2, 'D': 1}, 'port': 5002},
        'D': {'neighbors': {'B': 5, 'C': 1, 'E': 3}, 'port': 5003},
        'E': {'neighbors': {'D': 3}, 'port': 5004}
    }
    
    # Create router instances
    routers = {}
    for node_id, info in network.items():
        routers[node_id] = RouterNode(
            node_id=node_id,
            neighbors=info['neighbors'],
            port=info['port'],
            all_nodes=network
        )
    
    return routers

def test_routing_algorithms(routers):
    """Test the routing algorithms on the network."""
    # Let the network stabilize (LSAs propagate)
    print("\nWaiting for LSA propagation...")
    time.sleep(2)
    
    # Test Dijkstra's algorithm
    print("\n=== Testing Dijkstra's Algorithm ===")
    path_ae = routers['A'].request_route('E', 'dijkstra')
    path_db = routers['D'].request_route('B', 'dijkstra')
    
    # Test Flooding algorithm
    print("\n=== Testing Flooding Algorithm ===")
    path_ea = routers['E'].request_route('A', 'flooding')
    path_cd = routers['C'].request_route('D', 'flooding')
    
    # Print routing tables
    print("\n=== Routing Tables ===")
    for node_id, router in routers.items():
        graph = router.build_network_graph()
        print(f"\nRouter {node_id} knows about {len(graph)} nodes:")
        for n, neighbors in graph.items():
            print(f"  {n}: {neighbors}")

def main():
    """Main function to run the simulation."""
    print("=== Local Network Routing Simulation ===")
    print("Creating network with 5 routers (A, B, C, D, E)...")
    
    routers = create_network()
    
    # Start LSA flooding
    for router in routers.values():
        router.flood_lsa()
    
    # Test the routing algorithms
    test_routing_algorithms(routers)
    
    # Clean up
    for router in routers.values():
        router.stop()
    
    print("\nSimulation complete.")

if __name__ == "__main__":
    main()