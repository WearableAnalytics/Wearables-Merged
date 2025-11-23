package wplug

type Request struct {
	Message []byte // This is an encoded JSON
}

type Response struct {
	Err     error
	Message []byte
}

type Collector struct{}

func NewCollector() *Collector {
	return nil
}

func (c Collector) Collect(result Response) {
	//TODO implement me
	panic("implement me")
}

func (c Collector) Close() {
	//TODO implement me
	panic("implement me")
}
