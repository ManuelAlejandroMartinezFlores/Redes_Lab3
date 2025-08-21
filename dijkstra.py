import heapq

def dijkstra(graph, start, target):
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