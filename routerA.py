from router import *

if __name__ == "__main__":
    router = RouterNode("A", {"B":1}, 5000, {"A":{"port":5000}, "B":{"port":5001}, "C":{"port":5002}})

    print(f"=== Router A Started ===")
    print(f"Port: 5000")
    # print(f"Neighbors: {{config['neighbors']}}")
    print("\nType commands:")
    print("  'flood' - Flood LSA to neighbors")
    print("  'status' - Show current status")
    print("  'route <target> <algorithm>' - Calculate route (e.g., 'route E dijkstra')")
    print("  'ping <target>' - Send ping to target")
    print("  'quit' - Exit")
    
    try:
        while True:
            command = input("\nCommand: ").strip().lower()
            
            if command == 'flood':
                router.flood_lsa()
                print("LSA flooded to neighbors")
                
            elif command == 'status':
                router.print_topology()
                
            elif command.startswith('route '):
                parts = command.split()
                if len(parts) >= 3:
                    target = parts[1].upper()
                    algorithm = parts[2]
                    path, cost, algo = router.calculate_path(target, algorithm)
                    if path:
                        print(f"Path to {target}: {' → '.join(path)} (cost: {cost})")
                    else:
                        print(f"No path to {target} found")
                else:
                    print("Usage: route <target> <algorithm>")
                    
            elif command.startswith('ping '):
                parts = command.split()
                if len(parts) >= 2:
                    target = parts[1].upper()
                    if target in network_config:
                        router.send_message(target, {'type': 'PING', 'source': node_id, 'target': target})
                        print(f"Ping sent to {target}")
                    else:
                        print(f"Unknown target: {target}")
                else:
                    print("Usage: ping <target>")
                    
            elif command == 'quit':
                break
                
            else:
                print("Unknown command")
                
    except KeyboardInterrupt:
        print("\\nShutting down...")
    finally:
        router.stop()