# C4 Model for the old system

To get to know the [C4 model](https://c4model.com) I've started modelling the old system.

I am using [structurizr](https://docs.structurizr.com/quickstart) to do this.

## How to view the visualisation

Open a terminal and change to this directory, then run:

```sh
docker run -it --rm -p 8080:8080 -v $(pwd):/usr/local/structurizr structurizr/lite
```

Then you can open <http://localhost:8080/workspace/diagrams> in your browser.

Alternatively you could use the online version at <https://structurizr.com/dsl>
