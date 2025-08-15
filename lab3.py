import heapq
from collections import deque

class LinkStateRouter:
    def __init__(self, graph, router_id):
        self.graph = {k: dict(v) for k, v in graph.items()}  
        self.router_id = router_id
        self.link_state_db = {}  
        self.seq_num = 0  
        
        self.update_link_state()
    
    def update_link_state(self):
        self.link_state_db[self.router_id] = {
            'seq_num': self.seq_num,
            'neighbors': dict(self.graph[self.router_id]) 
        }
    
    def flood_link_state(self):
        self.seq_num += 1
        self.update_link_state()
        
        lsa = {
            'source': self.router_id,
            'seq_num': self.seq_num,
            'neighbors': dict(self.graph[self.router_id])
        }
        
        packet_counter = 0
        visited = set()
        queue = deque()
        
        for neighbor in self.graph[self.router_id]:
            queue.append((neighbor, self.router_id, lsa))
            packet_counter += 1
        
        while queue:
            current_node, incoming_node, current_lsa = queue.popleft()
            
            if (current_node, current_lsa['source']) in visited:
                continue
            visited.add((current_node, current_lsa['source']))
            
            if (current_lsa['source'] not in self.link_state_db or 
                current_lsa['seq_num'] > self.link_state_db[current_lsa['source']]['seq_num']):
                self.link_state_db[current_lsa['source']] = {
                    'seq_num': current_lsa['seq_num'],
                    'neighbors': dict(current_lsa['neighbors'])
                }
            
            for neighbor in self.graph[current_node]:
                if neighbor != incoming_node:
                    queue.append((neighbor, current_node, current_lsa))
                    packet_counter += 1
        
        return packet_counter
    
    def build_network_graph(self):
        network_graph = {}
        for router, info in self.link_state_db.items():
            network_graph[router] = dict(info['neighbors'])
        return network_graph
    
    def calculate_path(self, target, algorithm='dijkstra'):
        full_graph = self.build_network_graph()
        
        if algorithm == 'dijkstra':
            path, cost = self._dijkstra(full_graph, self.router_id, target)
            return path, cost, 'dijkstra'
        elif algorithm == 'flooding':
            paths, packets = self._flooding(full_graph, self.router_id, target)
            return (paths[0] if paths else []), packets, 'flooding'
        else:
            raise ValueError("Invalid algorithm. Choose 'dijkstra' or 'flooding'.")
    
    @staticmethod
    def _dijkstra(graph, start, target):
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
        
        path = []
        node = target
        while node is not None:
            path.append(node)
            node = previous_nodes[node]
        path = path[::-1]
        
        return (path, distances[target]) if path and path[0] == start else ([], float('infinity'))
    
    @staticmethod
    def _flooding(graph, start, target):
        if start not in graph or target not in graph:
            return [], 0
        
        visited = {}
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
            
            if current_node not in visited:
                visited[current_node] = set()
            visited[current_node].add(incoming_node)
            
            for neighbor in graph[current_node]:
                if neighbor != incoming_node:
                    new_path = path.copy()
                    new_path.append(neighbor)
                    queue.append((neighbor, new_path, current_node))
                    packet_counter += 1
        
        return paths, packet_counter

    def get_routing_table(self):
        full_graph = self.build_network_graph()
        routing_table = {}
        
        for destination in full_graph:
            if destination != self.router_id:
                path, cost = self._dijkstra(full_graph, self.router_id, destination)
                next_hop = path[1] if len(path) > 1 else None
                routing_table[destination] = {
                    'next_hop': next_hop,
                    'cost': cost,
                    'path': path
                }
        
        return routing_table

def print_routing_table(router):
    print(f"\nRouting Table for Router {router.router_id}:")
    print("{:<10} {:<10} {:<10} {}".format("Destination", "Next Hop", "Cost", "Path"))
    print("-" * 50)
    for dest, info in router.get_routing_table().items():
        path_str = " → ".join(info['path'])
        print("{:<10} {:<10} {:<10} {}".format(
            dest, 
            info['next_hop'] or 'N/A', 
            info['cost'], 
            path_str
        ))

