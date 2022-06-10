
function DirTree() {
    let trees = $('.DirTree')
    if (!trees.length)
        return;

    let pathentries = SauceryServicePathEntries.filter(p => p);

    trees.each(function () {
        let t = $(this);
        let name = t.attr('saucery-tree-name');
        let href = t.attr('saucery-tree-href');
        let div = $('<div>').addClass('anchors').appendTo(t);
        let up = '../'.repeat(pathentries.length);

        $('<a>').text(name).attr('href', up + href).appendTo(div);
    });

    let treename = pathentries.at(0);
    if (!treename)
        return;

    tree = trees.filter('[saucery-tree-href=' + treename + ']')
    if (!tree.length)
        return;

    let href = '';
    let anchors = pathentries.slice(1).reverse()
        .flatMap(function (name) {
            let a = $('<a>').attr('href', href).text(name);
            href = href + '../';
            return [a, $('<a>').text('/')];
        }).reverse();
    tree.children('div.anchors').append(anchors);

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
