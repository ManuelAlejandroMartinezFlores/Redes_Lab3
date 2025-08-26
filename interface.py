from router import *

def get_user_config():
    """Get configuration from user input."""
    print("=== Configuración del Router ===")
    
    # Basic configuration
    node_id = input("ID del router (ej: A): ").strip()
    neighbors_input = input("Vecinos (separados por coma, ej: B,C): ").strip()
    neighbors = [n.strip() for n in neighbors_input.split(',')] if neighbors_input else []
    
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
    
    return node_id, neighbors, algorithm, path_algorithm

if __name__ == "__main__":
    # Configuración de Redis
    REDIS_CONFIG = {
        'host': 'localhost',
        'port': 6379,
        'password': None
    }
    
    # Obtener configuración del usuario
    ROUTER_ID, NEIGHBORS, ALGORITHM, PATH_ALGORITHM = get_user_config()
    ROUTER_CONFIG = {
        'algorithm': ALGORITHM,
        'routing_algorithm': PATH_ALGORITHM
    }
    
    # Crear instancia del router
    router = RouterNode(ROUTER_ID, NEIGHBORS, REDIS_CONFIG, ROUTER_CONFIG)
    
    print(f"\n=== Router {ROUTER_ID} Iniciado ===")
    print(f"Conectado a Redis: {REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}")
    print(f"Vecinos: {NEIGHBORS}")
    print(f"Algoritmo de enrutamiento: {ALGORITHM}")
    if ALGORITHM == 'link_state':
        print(f"Algoritmo de cálculo de ruta: {PATH_ALGORITHM}")
    
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
    if ALGORITHM == 'link_state':
        algorithm_specific_commands = [
            "'flood' - Flood LSA a vecinos",
            "'algorithm <dijkstra|flooding>' - Cambiar algoritmo de camino"
        ]
    elif ALGORITHM == 'distance_vector':
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
                
            elif command == 'flood' and ALGORITHM == 'link_state':
                router.flood_lsa()
                print("LSA enviado a vecinos")
                
            elif command == 'update' and ALGORITHM == 'distance_vector':
                router.broadcast_distance_vector()
                print("Vector de distancias actualizado y enviado")
                
            elif command.startswith('algorithm ') and ALGORITHM == 'link_state':
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