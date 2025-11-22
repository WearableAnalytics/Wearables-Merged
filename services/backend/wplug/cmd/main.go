package main

import "log"

func main() {
	log.SetPrefix("wplug: ")
	log.SetFlags(log.LstdFlags | log.Lshortfile)

}
