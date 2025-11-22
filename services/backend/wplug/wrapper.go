package wplug

type Request struct {
	Message []byte // This is an encoded JSON
}

type Response struct {
	Err     error
	Message []byte
}
