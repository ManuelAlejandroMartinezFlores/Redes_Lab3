import socket
import threading
import json
import time
from dijkstra import *
from flooding import *
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
        self.socket.settimeout(1.0)  # Add timeout to prevent blocking
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
        try:
            self.socket.sendto(json.dumps(message).encode(), ('localhost', dest_port))
        except Exception as e:
            print(f"{self.node_id}: Error sending to {destination_id}: {str(e)}")
    
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
        
        print(f"{self.node_id}: Flooding LSA (seq {self.seq_num}) to neighbors: {list(self.neighbors.keys())}")
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
                    
            except socket.timeout:
                continue  # Just continue on timeout
            except json.JSONDecodeError:
                print(f"{self.node_id}: Error decoding message")
            except Exception as e:
                if self.running:  # Only print errors if we're still running
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
            
            print(f"{self.node_id}: Updated topology with {source}'s info")
            
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
        print(f"\n{self.node_id}'s known topology ({len(graph)} nodes):")
        for node, neighbors in graph.items():
            print(f"  {node}: {neighbors}")
    
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
        print(f"Created router {node_id} on port {info['port']}")
    
    return routers

def test_routing_algorithms(routers):
    """Test the routing algorithms on the network."""
    # Let the network stabilize (LSAs propagate)
    print("\nWaiting for LSA propagation (3 seconds)...")
    time.sleep(3)
    
    # Print each router's topology view
    print("\n=== Network Topology Views ===")
    for router in routers.values():
        router.print_topology()
    
    # Test Dijkstra's algorithm
    print("\n" + "="*50)
    print("TESTING DIJKSTRA'S ALGORITHM")
    print("="*50)
    
    test_cases = [
        ('A', 'E'),  # A → C → D → E (cost: 4+1+3=8)
        ('D', 'B'),  # D → C → B (cost: 1+2=3)
        ('E', 'C'),  # E → D → C (cost: 3+1=4)
        ('B', 'A'),  # B → A (cost: 1)
    ]
    
    for start, target in test_cases:
        path = routers[start].request_route(target, 'dijkstra')
    
    # Test Flooding algorithm
    print("\n" + "="*50)
    print("TESTING FLOODING ALGORITHM")
    print("="*50)
    
    # Use smaller test cases for flooding to avoid too many packets
    flooding_test_cases = [
        ('A', 'D'),  # Should find A → B → D or A → C → D
        ('E', 'B'),  # Should find E → D → C → B
        ('C', 'A'),  # Should find C → A
    ]
    
    for start, target in flooding_test_cases:
        path = routers[start].request_route(target, 'flooding')
        time.sleep(0.5)  # Small delay between tests

def main():
    """Main function to run the simulation."""
    print("=== Local Network Routing Simulation ===")
    print("Creating network with 5 routers (A, B, C, D, E)...")
    
    routers = create_network()
    
    # Start LSA flooding
    print("\nStarting LSA flooding...")
    for router in routers.values():
        router.flood_lsa()
    
    # Wait a moment for initial flooding
    time.sleep(2)
    
    # Test the routing algorithms
    test_routing_algorithms(routers)
    
    # Clean up
    print("\nShutting down routers...")
    for router in routers.values():
        router.stop()
    
    print("Simulation complete.")

if __name__ == "__main__":
    main()