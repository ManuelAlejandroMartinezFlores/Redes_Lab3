from router import *

if __name__ == "__main__":
    # Configuración de Redis del laboratorio
    REDIS_CONFIG = {
        'host': 'localhost',
        'port': 6379,
        'password': None
    }
    
    # Información del nodo (debería venir de los archivos de configuración)
    ROUTER_ID = "sec10.grupo0.A"  # Ejemplo usando el formato especificado
    NEIGHBORS = ["sec10.grupo0.B"]  # Vecinos iniciales
    
    # Crear instancia del router con Redis
    router = RouterNode(ROUTER_ID, NEIGHBORS, REDIS_CONFIG)
    
    print(f"=== Router {ROUTER_ID} Started ===")
    print(f"Conectado a Redis: {REDIS_CONFIG['host']}:{REDIS_CONFIG['port']}")
    print("Vecinos iniciales:", NEIGHBORS)
    print("\nIngrese comando:")
    print("  'flood' - Flood LSA a vecinos")
    print("  'topo' - Topología conocida")
    print("  'route <objetivo> <algoritmo>' - Calcula la ruta (e.g., 'route D dijkstra')")
    print("  'ping <objetivo>' - Enviar ping")
    print("  'send <objetivo> <mensaje>' - Enviar mensaje")
    print("  'quit' - Salir")
    
    try:
        while True:
            command = input("\nCommand: ").strip()
            
            if command == 'flood':
                router.flood_lsa()
                print("LSA flooded to neighbors")
                
            elif command == 'topo':
                router.print_topology()
                
            elif command.startswith('route '):
                parts = command.split()
                if len(parts) >= 3:
                    target = parts[1]  # Ya no necesita uppercase con el nuevo formato
                    algorithm = parts[2]
                    path = router.request_route(target, algorithm)
                else:
                    print("Usage: route <target> <algorithm>")
                    
            elif command.startswith('ping '):
                parts = command.split()
                if len(parts) >= 2:
                    target = parts[1]
                    router.send_hello(target)
                    print(f"Ping enviado a {target}")
                else:
                    print("Usage: ping <target>")
                    
            elif command.startswith('send '):
                parts = command.split(' ', 2)  # Dividir solo en los primeros dos espacios
                if len(parts) >= 3:
                    target = parts[1]
                    message = parts[2]
                    router.send_data(target, message)
                    print(f"Mensaje enviado a {target}")
                else:
                    print("Usage: send <target> <message>")
                    
            elif command == 'quit':
                break
                
            else:
                print("Comando desconocido. Comandos disponibles: flood, topo, route, ping, send, quit")
                
    except KeyboardInterrupt:
        print("\nApagando...")
    finally:
        router.stop()