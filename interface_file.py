from router import *
import json
import os

def load_config_from_files(topo_file, names_file, user_id):
    """
    Load configuration from topo.txt and names.txt files.
    Only extracts the node ID and neighbors for the current user.
    
    Args:
        topo_file (str): Path to topo.txt file
        names_file (str): Path to names.txt file  
        user_id (str): User's UVG ID to find their node assignment
    
    Returns:
        dict: Configuration containing node_id and neighbors
    """
    config = {
        'node_id': None,
        'neighbors': []
    }
    
    try:
        # Load names file first to find user's node assignment
        if os.path.exists(names_file):
            with open(names_file, 'r') as f:
                names_data = json.load(f)
            if names_data.get('type') == 'names' and 'config' in names_data:
                print(f"Names file loaded: {len(names_data['config'])} assignments")
                
                # Find which node is assigned to this user
                user_node = None
                for node, assigned_user in names_data['config'].items():
                    if assigned_user == user_id:
                        user_node = node
                        break
                
                if user_node:
                    config['node_id'] = user_node
                    print(f"Usuario {user_id} asignado al nodo {user_node}")
                else:
                    print(f"User {user_id} not found in names file")
                    return None
            else:
                print("Invalid names file format")
                return None
        else:
            print(f"Names file not found: {names_file}")
            return None
        
        # Load topology file to get neighbors for this node
        if os.path.exists(topo_file):
            with open(topo_file, 'r') as f:
                topo_data = json.load(f)
            
            if topo_data.get('type') == 'topo' and 'config' in topo_data:
                print(f"Topology file loaded: {len(topo_data['config'])} nodes")
                
                # Get neighbors for this node
                if config['node_id'] in topo_data['config']:
                    config['neighbors'] = topo_data['config'][config['node_id']]
                    config['neighbors'] = [names_data['config'][n] for n in config['neighbors']]
                    print(f"Nodo {config['node_id']} tiene vecinos: {config['neighbors']}")
                else:
                    print(f"Node {config['node_id']} not found in topology")
                    return None
            else:
                print("Invalid topology file format")
                return None
        else:
            print(f"Topology file not found: {topo_file}")
            return None
            
        return config
        
    except json.JSONDecodeError as e:
        print(f"JSON decode error: {e}")
        return None
    except Exception as e:
        print(f"Error loading configuration: {e}")
        return None

def get_user_config():
    """Get configuration from user input and files."""
    print("=== Configuración del Router ===")
    
    # Get user ID
    user_id = input("Tu usuario: ").strip()
    if not user_id:
        print("Se requiere usuario")
        return None
    
    # Get file paths
    topo_file = input("Ruta al archivo topo.txt (presiona Enter para 'topo.txt'): ").strip()
    names_file = input("Ruta al archivo names.txt (presiona Enter para 'names.txt'): ").strip()
    
    # Default file names
    topo_file = topo_file if topo_file else 'topo.txt'
    names_file = names_file if names_file else 'names.txt'
    
    # Load configuration from files
    config = load_config_from_files(topo_file, names_file, user_id)
    if not config:
        return None
    
    # Algorithm selection
    print("\nSelección de algoritmo de enrutamiento:")
    print("1. distance_vector - Algoritmo de vector de distancias")
    print("2. link_state - Algoritmo de estado de enlace")
    algorithm_choice = input("Elija algoritmo (1/2 o nombre): ").strip().lower()
    
    if algorithm_choice in ['1', 'distance_vector', 'dv']:
        algorithm = 'distance_vector'
        path_algorithm = None
    elif algorithm_choice in ['2', 'link_state', 'ls']:
        algorithm = 'link_state'
        # Ask for path algorithm if using link state
        print("\nSelección de algoritmo de cálculo de ruta:")
        print("1. dijkstra - Algoritmo de Dijkstra (óptimo)")
        print("2. flooding - Algoritmo de flooding (descubrimiento)")
        path_choice = input("Elija algoritmo de camino (1/2): ").strip().lower()
        path_algorithm = 'dijkstra' if path_choice in ['1', 'dijkstra'] else 'flooding'
    else:
        print("Usando algoritmo por defecto: distance_vector")
        algorithm = 'distance_vector'
        path_algorithm = None
    
    return {
        'node_id': config['node_id'],
        'neighbors': config['neighbors'],
        'router_config': {
            'algorithm': algorithm,
            'routing_algorithm': path_algorithm
        },
        'user_id': user_id
    }

if __name__ == "__main__":
    # Configuración de Redis
    REDIS_CONFIG = {
        'host': 'lab3.redesuvg.cloud',
        'port': 6379,
        'password': 'UVGRedis2025'
    }
    
    # Obtener configuración
    config = get_user_config()
    if not config:
        print("Error en configuración. Saliendo...")
        exit(1)
    
    # Crear instancia del router
    router = RouterNode(
        config['user_id'], 
        config['neighbors'], 
        REDIS_CONFIG, 
        config['router_config']
    )
    
    print(f"\n=== Router {config['node_id']}: {config['user_id']} Iniciado ===")
    print(f"Conectado a Redis: {REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}")
    print(f"Vecinos: {config['neighbors']}")
    print(f"Algoritmo de enrutamiento: {config['router_config']['algorithm']}")
    if config['router_config']['algorithm'] == 'link_state':
        print(f"Algoritmo de cálculo de ruta: {config['router_config']['routing_algorithm']}")
    
    # Comandos comunes
    common_commands = [
        "'info' - Mostrar información de enrutamiento",
        "'send <objetivo> <mensaje>' - Enviar mensaje",
        "'ping <objetivo>' - Enviar ping",
        "'route <objetivo>' - Mostrar ruta a objetivo",
        "'quit' - Salir"
    ]
    
    # Comandos específicos por algoritmo
    algorithm_specific_commands = []
    if config['router_config']['algorithm'] == 'link_state':
        algorithm_specific_commands = [
            "'flood' - Flood LSA a vecinos",
            "'algorithm <dijkstra|flooding>' - Cambiar algoritmo de camino"
        ]
    elif config['router_config']['algorithm'] == 'distance_vector':
        algorithm_specific_commands = [
            "'update' - Forzar actualización de vector de distancias"
        ]
    
    # Mostrar todos los comandos
    print("\nComandos disponibles:")
    for cmd in common_commands + algorithm_specific_commands:
        print(f"  {cmd}")
    
    try:
        while True:
            command = input("\nComando: ").strip()
            
            if command == 'info':
                router.print_routing_info()
                
            elif command == 'flood' and config['router_config']['algorithm'] == 'link_state':
                router.flood_lsa()
                print("LSA enviado a vecinos")
                
            elif command == 'update' and config['router_config']['algorithm'] == 'distance_vector':
                router.broadcast_distance_vector()
                print("Vector de distancias actualizado y enviado")
                
            elif command.startswith('algorithm ') and config['router_config']['algorithm'] == 'link_state':
                parts = command.split()
                if len(parts) >= 2:
                    new_algorithm = parts[1]
                    router.set_routing_algorithm(new_algorithm)
                else:
                    print("Uso: algorithm <dijkstra|flooding>")
                    
            elif command.startswith('send '):
                parts = command.split(' ', 2)
                if len(parts) >= 3:
                    target = parts[1]
                    message = parts[2]
                    success = router.send_data(target, message)
                    if success:
                        print(f"Mensaje enviado a {target}")
                    else:
                        print(f"Error: No se pudo enviar mensaje a {target}")
                else:
                    print("Uso: send <objetivo> <mensaje>")
                    
            elif command.startswith('ping '):
                parts = command.split()
                if len(parts) >= 2:
                    target = parts[1]
                    router.send_hello(target)
                    print(f"Ping enviado a {target}")
                else:
                    print("Uso: ping <objetivo>")
                    
            elif command.startswith('route '):
                parts = command.split()
                if len(parts) >= 2:
                    target = parts[1]
                    router.request_route(target)
                else:
                    print("Uso: route <objetivo>")
                    
            elif command == 'quit':
                break
                
            else:
                print("Comando desconocido. Comandos disponibles:")
                for cmd in common_commands + algorithm_specific_commands:
                    print(f"  {cmd}")
                
    except KeyboardInterrupt:
        print("\nApagando router...")
    finally:
        router.stop()
