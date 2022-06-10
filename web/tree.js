
$(Tree);

function Tree() {
    let trees = $('.Tree')
    if (!trees.length)
        return;

    let sospath = SauceryServicePath.split('/').filter(p => p).reverse();
    let treename = sospath.at(0);
    sospath = sospath.slice(1);

    trees.each(function () {
        let t = $(this);
        let name = t.attr('saucery-tree-name');
        let href = t.attr('saucery-tree-href');

        if (treename) {
            if (treename == href)
                href = '.';
            else
                href = '../' + href;
        }
        $('<a>').text(name).attr('href', href).appendTo(t);
    });

    if (!treename)
        return;

    tree = trees.filter('[saucery-tree-href=' + treename + ']')
    if (!tree.length)
        return;

    let href = '';
    let anchors = sospath.flatMap(function (name) {
        let a = $('<a>').attr('href', href).text(name);
        href = href + '../';
        return [a, $('<a>').text('/')];
    }).slice(0, -1).reverse();
    $('<div>').append(anchors).appendTo(tree);

    let jstree_data = function (obj, callback) {
        let path = this.get_path(obj, '/') || '';
        $.getJSON(path, {'format': 'json'}, function (data) {
            callback(data.map(function (child) {
                let href = (path ? path + '/' : '') + encodeURIComponent(child.name);
                return {
                    'text': child.name,
                    'icon': false,
                    'a_attr': {
                        'href': href,
                    },
                    'href': href,
                    'children': child.type == 'directory',
                }
            }));
        });
    };

    $('<div>').jstree({'core': {'data': jstree_data}})
        .on('select_node.jstree', (evt, data) => window.location = data.node.original.href)
        .appendTo(tree);
}
