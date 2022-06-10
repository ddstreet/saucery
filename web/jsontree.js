
function JsonTree() {
    $('.JsonTree').each(function () {
        let t = $(this);
        let name = t.attr('saucery-tree-name');
        let json = t.attr('saucery-tree-json');
        let ul = $('<ul>').appendTo(t);
        let li = $('<li>').text(name).appendTo(ul);

        $.getJSON(json, {format: 'json'}, (data => PopulateJsonTree(t, li, data)));
    });
}

function JsonEntry(parent, node) {
    if (node === null || node === undefined)
        return;

    if (Array.isArray(node)) {
        let ul = $('<ul>').appendTo(parent);
        node.forEach(function (n) {
            let li = $('<li>').appendTo(ul);
            JsonEntry(li, n);
        });
    } else if (typeof(node) == 'object') {
        let ul = $('<ul>').appendTo(parent);
        Object.keys(node).forEach(function (key) {
            let li = $('<li>').appendTo(ul);
            let a = $('<a>').text(key).appendTo(li);
            let value = node[key];

            if (Array.isArray(value) || typeof(value) == 'object')
                JsonEntry(li, value);
            else
                a.text(key + ': ' + value);
        });
    } else {
        $('<a>').text(node).appendTo(parent);
    }
}

function PopulateJsonTree(tree, parent, data) {
    JsonEntry(parent, data);

    tree.jstree({
        'core': {
            'themes': {
                'icons': false,
            },
        },
    });
}
