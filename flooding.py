from collections import deque

def flooding_paths(graph, start, target, max_hops=10):
    """
    Flooding algorithm implementation with cycle detection and hop limit.
    
    Args:
        max_hops: Maximum number of hops to prevent infinite loops
    """
    if start not in graph or target not in graph:
        return [], 0
    
    paths = []
    packet_counter = 0
    visited_paths = set()  # Track visited paths to prevent cycles
    
    queue = deque()
    initial_path = (start,)
    queue.append((start, [start], None, 0))  # (current_node, path, incoming_node, hops)
    packet_counter += 1
    visited_paths.add(initial_path)
    
    while queue:
        current_node, path, incoming_node, hops = queue.popleft()
        
        if current_node == target:
            paths.append(path)
            continue
        
        # Stop if we've exceeded maximum hops
        if hops >= max_hops:
            continue
        
        for neighbor in graph[current_node]:
            if neighbor != incoming_node:
                new_path = path.copy()
                new_path.append(neighbor)
                path_tuple = tuple(new_path)
                
                # Only explore if we haven't seen this exact path before
                if path_tuple not in visited_paths:
                    visited_paths.add(path_tuple)
                    queue.append((neighbor, new_path, current_node, hops + 1))
                    packet_counter += 1
    
    return paths, packet_counter